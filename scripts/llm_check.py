"""Benchmark the local Ollama models on the JSON tasks the pipeline uses.

    python scripts/llm_check.py                 # every installed model
    python scripts/llm_check.py --model granite4.2:3b --extended
    python scripts/llm_check.py --budget 240    # total seconds across models

Reports per-call latency (p50/p95), JSON validity, accuracy on canned labels, GPU residency
(/api/ps size_vram), and a recommendation. Never pulls models.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from otr.cue_detector import RETRO_PROMPT                      # noqa: E402
from otr.llm import (DEFAULT_MODEL, SENSITIVITY_PROMPT, OllamaLLM, default_host,   # noqa: E402
                     default_model, extract_json)
from otr.state_machine import TOPIC_PROMPT                      # noqa: E402

# (text, expected_sensitive)
CANNED_SENSITIVITY = [
    ("My doctor says the biopsy came back and I need surgery next month.", True),
    ("We're giving Marcus a raise to 185 thousand starting in March.", True),
    ("HR opened an investigation into the complaint against Jenna.", True),
    ("The roadmap review is on Thursday at ten.", False),
    ("Let's move the standup to 9:30 so the London team can join.", False),
]

# 20 varied sentences, kept separate from the few-shot examples in SENSITIVITY_PROMPT.
EXTENDED_SENSITIVITY = [
    ("Honestly I've been struggling with depression since the spring.", True),
    ("Our CFO told me privately that Alex's bonus this year is 40 percent of base.", True),
    ("Between us, the board is planning to close the Austin office in January.", True),
    ("We have to let go of about twelve people from support next quarter.", True),
    ("Her visa application was denied so she may have to leave the country.", True),
    ("Tom has been late every day and we're drafting a written warning for him.", True),
    ("My wife and I are separating, so I'll be working odd hours.", True),
    ("Legal says the settlement with the former contractor is two hundred thousand.", True),
    ("Nadia is pregnant but hasn't told the team yet.", True),
    ("I'm on antidepressants and the new dose makes me tired in the mornings.", True),
    ("We launched a salary calculator for candidates last week.", False),
    ("The health insurance enrollment deadline is November 15th.", False),
    ("Our legal team reviewed the new terms of service and they are live now.", False),
    ("The hospital customer wants a dashboard for bed occupancy.", False),
    ("Reminder that the quarterly performance review forms are due Friday.", False),
    ("We're hiring two engineers and the compensation bands are on the wiki.", False),
    ("The doctor appointment booking feature needs a calendar sync fix.", False),
    ("Let's discuss the layoffs-tracking dashboard bug in the Jira board.", False),
    ("Parental leave policy is in the handbook for anyone who wants to read it.", False),
    ("The retro covered deployment speed and the flaky integration tests.", False),
]

CANNED_RETRACT = [   # (cue, candidates, expected ids)
    ("Sorry, scratch what I said about the Henderson pricing.",
     "s1: The kickoff went well and the team is excited.\ns2: The Henderson contract is priced at 90 thousand a year.\ns3: Next sprint we focus on search.",
     ["s2"]),
    ("Please remove my comment about Lena's medical leave from the notes.",
     "a1: Lena will be on medical leave for six weeks starting Monday.\na2: We need someone to cover her on-call rotation.\na3: The office wifi is flaky again.",
     ["a1"]),
]

CANNED_SCOPE = [   # (scope, next utterance, expected topic_changed)
    ("We were discussing Priya's performance plan and whether to fire her.",
     "Okay, let's move on to the Q3 launch schedule.", True),
    ("We were discussing Priya's performance plan and whether to fire her.",
     "I think she needs another month before we decide anything about her role.", False),
]


def http_json(host, path, timeout=5):
    with urllib.request.urlopen(host + path, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def pct(vals, p):
    if not vals:
        return float("nan")
    vals = sorted(vals)
    return vals[min(len(vals) - 1, int(round(p / 100 * (len(vals) - 1))))]


def build_tasks(extended):
    tasks = []
    sens = CANNED_SENSITIVITY + (EXTENDED_SENSITIVITY if extended else [])
    for text, exp in sens:
        tasks.append(("sensitivity", SENSITIVITY_PROMPT.format(text=text), lambda o, e=exp: isinstance(o, dict) and
                      "sensitive" in o and bool(o["sensitive"]) == e, exp))
    for cue, cands, exp in CANNED_RETRACT:
        tasks.append(("retract", RETRO_PROMPT.format(cue=cue, cands=cands), lambda o, e=exp: isinstance(o, dict) and
                      sorted(map(str, o.get("ids", []))) == e, None))
    for scope, text, exp in CANNED_SCOPE:
        tasks.append(("scope_end", TOPIC_PROMPT.format(scope=scope, text=text), lambda o, e=exp: isinstance(o, dict) and
                      o.get("topic_changed") is e, None))
    return tasks


def evaluate(model, host, extended, deadline):
    llm = OllamaLLM(model=model, host=host, timeout=60.0)
    tasks = build_tasks(extended)
    cold = llm.warmup()
    lat, valid, correct, n = [], 0, 0, 0
    tp = fp = tn = fn = 0
    for kind, prompt, check, exp in tasks:
        if time.time() > deadline:
            print(f"  (time budget reached after {n} calls)")
            break
        t0 = time.perf_counter()
        try:
            out = llm.complete(prompt, use_cache=False)
        except Exception as e:
            out = ""
            print(f"  call failed: {e}")
        lat.append(time.perf_counter() - t0)
        obj = extract_json(out)
        n += 1
        valid += obj is not None
        ok = bool(check(obj)) if obj is not None else False
        if not ok:
            print(f"  MISS [{kind}] {prompt.splitlines()[-2][:90] if kind == 'sensitivity' else ''} -> {out[:80]!r}")
        correct += ok
        if kind == "sensitivity" and obj is not None:
            pred = bool(obj.get("sensitive")) if isinstance(obj, dict) else False
            tp += pred and exp
            fp += pred and not exp
            tn += (not pred) and (not exp)
            fn += (not pred) and exp
        elif kind == "sensitivity":
            fn += bool(exp)
            tn += not exp
    vram = None
    try:
        for m in llm.ps():
            if m["name"].split(":")[0] == model.split(":")[0]:
                vram = (m.get("size_vram", 0), m.get("size", 0))
    except Exception:
        pass
    llm.close()
    return dict(model=model, cold=cold, lat=lat, n=n, valid=valid, correct=correct,
                tp=tp, fp=fp, tn=tn, fn=fn, vram=vram)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", action="append", help="limit to these models (repeatable)")
    ap.add_argument("--host", default=default_host())
    ap.add_argument("--budget", type=float, default=240.0, help="total seconds across all models")
    ap.add_argument("--extended", action="store_true", help="add 20 varied sensitivity sentences")
    a = ap.parse_args()

    try:
        installed = [m["name"] for m in http_json(a.host, "/api/tags")["models"]]
    except Exception as e:
        print(f"Ollama not reachable at {a.host}: {e}")
        return 2
    print(f"Ollama at {a.host}; installed: {', '.join(installed) or '(none)'}")
    want = default_model()
    if want not in installed and f"{want}:latest" not in installed:
        print(f"WARNING: default model {want!r} is not installed (run `ollama pull {want}` yourself if wanted).")
    models = a.model or installed
    if not models:
        return 1
    t_start = time.time()
    results = []
    for i, m in enumerate(models):
        deadline = t_start + a.budget * (i + 1) / len(models)
        print(f"\n== {m}")
        r = evaluate(m, a.host, a.extended, deadline)
        results.append(r)
        lat = r["lat"]
        print(f"  cold load+first call: {r['cold']:.1f}s")
        print(f"  latency  p50 {pct(lat, 50):.2f}s  p95 {pct(lat, 95):.2f}s  mean {statistics.mean(lat) if lat else 0:.2f}s  (n={r['n']})")
        print(f"  JSON validity {r['valid']}/{r['n']}   task accuracy {r['correct']}/{r['n']}")
        pos, neg = r["tp"] + r["fn"], r["fp"] + r["tn"]
        if pos + neg:
            print(f"  sensitivity: recall {r['tp']}/{pos}   false-positive rate {r['fp']}/{neg}")
        v = r["vram"]
        if v:
            print(f"  GPU: size_vram {v[0] / 1e9:.2f} GB of {v[1] / 1e9:.2f} GB loaded ({'fully on GPU' if v[0] >= v[1] else 'partly CPU'})")
        else:
            print("  GPU: model not listed in /api/ps")

    print("\n== recommendation")
    good = [r for r in results if r["n"] and r["valid"] == r["n"] and r["correct"] / r["n"] >= 0.8
            and pct(r["lat"], 95) < 3.0]
    if good:
        best = max(good, key=lambda r: (r["correct"] / r["n"], -pct(r["lat"], 50)))
        print(f"Use OTR_LLM_MODEL={best['model']} (p95 {pct(best['lat'], 95):.2f}s, "
              f"accuracy {best['correct']}/{best['n']}).")
    else:
        print("No installed model meets valid-JSON + >=80% accuracy + p95 < 3 s. "
              f"Keep {DEFAULT_MODEL} with keyword fallback, or pull a faster/better model yourself.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
