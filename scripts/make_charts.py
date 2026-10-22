#!/usr/bin/env python3
"""Make the result charts in docs/images/charts/ from records in this repository.

    python scripts/make_charts.py            # writes five PNGs, prints what it read
    python scripts/make_charts.py --out DIR  # somewhere else

Inputs (read only; nothing is computed from data that is not in these files):
  bench/results_v2_sealed.json   OTR-Bench v2 sealed split, 150 items, aggregates only   -> leak_overremoval.png
  bench/results_v2_dev.json      OTR-Bench v2 dev split, 246 items                        -> leak_by_subtype.png
  bench/results_sweep.json       hold-length sweep on the old 47-item synthetic set       -> hold_sweep.png
  docs/RESEARCH.md               ConfAIde and PrivacyLens numbers (checked, then plotted) -> published_llm_leak.png
  docs/COMPETITORS.md            every grid cell cites a phrase that must appear there    -> capability_grid.png

Deterministic: fixed sizes, fixed DPI, no timestamps in the PNG metadata.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ACCENT = "#1a73e8"
ACCENT_PALE = "#d2e3fc"
GREY = "#9aa0a6"
GREY_PALE = "#eceff1"
INK = "#202124"
MUTED = "#5f6368"
DPI = 150

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 9,
    "axes.edgecolor": "#c4c7c5",
    "axes.labelcolor": INK,
    "axes.titlesize": 11,
    "axes.titleweight": "bold",
    "axes.titlecolor": INK,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "savefig.facecolor": "white",
    "svg.hashsalt": "otr",
})

SYSTEM_LABEL = {"A": "A: rules + PII", "B-stub": "B-stub", "B+-stub": "B+-stub", "C": "C: ours (no model)"}


def path(*p):
    return os.path.join(ROOT, *p)


def load(rel):
    with open(path(rel), encoding="utf-8") as f:
        return json.load(f)


def wilson(k, n, z=1.96):  # same z as bench/metrics.py
    if n == 0:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h


def footnote(fig, text):
    fig.text(0.01, 0.012, text, ha="left", va="bottom", fontsize=7, color=MUTED, wrap=True)


def save(fig, out, name):
    p = os.path.join(out, name)
    fig.savefig(p, dpi=DPI, metadata={"Software": None})
    plt.close(fig)
    print("wrote", os.path.relpath(p, ROOT))


def ci_check(m):
    lo, hi = wilson(m["k"], m["n"])
    assert abs(lo - m["lo"]) < 1e-6 and abs(hi - m["hi"]) < 1e-6, "Wilson interval in file does not match"


# (a) leak and over-removal on v2 sealed
def chart_sealed(out):
    src = "bench/results_v2_sealed.json"
    d = load(src)
    systems = ["A", "B-stub", "B+-stub", "C"]
    fig, axes = plt.subplots(1, 2, figsize=(8.4, 3.6))
    panels = [("Leak", "Leak: items where a private line\nreached the notes"),
              ("Omit-Public", "Over-removal: items that lost\na public line")]
    for ax, (key, title) in zip(axes, panels):
        rates, los, his, labels = [], [], [], []
        for s in systems:
            m = d["systems"][s]["breakdown"]["ALL"][key]
            ci_check(m)
            rates.append(m["rate"] * 100)
            los.append((m["rate"] - m["lo"]) * 100)
            his.append((m["hi"] - m["rate"]) * 100)
            labels.append(f"{m['k']}/{m['n']}")
        colors = [ACCENT if s == "C" else GREY for s in systems]
        x = range(len(systems))
        ax.bar(x, rates, width=0.6, color=colors, yerr=[los, his], capsize=3,
               error_kw={"ecolor": INK, "elinewidth": 1, "capthick": 1})
        for i, (r, up, lab) in enumerate(zip(rates, his, labels)):
            ax.text(i, r + up + 2, f"{r:.0f}%\n{lab}", ha="center", va="bottom", fontsize=7.5, color=INK)
        ax.set_xticks(list(x), [SYSTEM_LABEL[s] for s in systems], fontsize=7.5)
        ax.set_ylim(0, 112)
        ax.set_yticks([0, 20, 40, 60, 80, 100])
        ax.set_ylabel("percent of items")
        ax.set_title(title, fontsize=9.5, loc="left")
        ax.grid(axis="y", color="#e8eaed", linewidth=0.8)
        ax.set_axisbelow(True)
    fig.suptitle("OTR-Bench v2 sealed split (150 items): lower is better on both",
                 x=0.01, ha="left", fontsize=11, fontweight="bold", color=INK)
    footnote(fig, f"Source: {src} (llm none, hold 30 s). Bars: Wilson 95% intervals. B-stub and B+-stub are "
                  "heuristic stand-ins, not LLMs. Data written by language models, not reviewed by people.")
    fig.tight_layout(rect=(0, 0.07, 1, 0.94))
    save(fig, out, "leak_overremoval.png")
    return {s: d["systems"][s]["breakdown"]["ALL"]["Leak"]["rate"] for s in systems}


# (b) leak by subtype on v2 dev, C vs the best baseline
def chart_subtype(out):
    src = "bench/results_v2_dev.json"
    d = load(src)
    baselines = ["A", "B-stub", "B+-stub"]
    best = min(baselines, key=lambda s: (d["systems"][s]["breakdown"]["ALL"]["Leak"]["rate"], s))
    sub_c = d["systems"]["C"]["by"]["subtype"]
    sub_b = d["systems"][best]["by"]["subtype"]
    rows = []
    for st in sorted(sub_c):
        mc, mb = sub_c[st]["Leak"], sub_b[st]["Leak"]
        if mc["n"] >= 8:
            rows.append((st, mc, mb))
    rows.sort(key=lambda r: (r[1]["rate"], r[0]))
    fig, ax = plt.subplots(figsize=(7.6, 0.42 * len(rows) + 1.6))
    h = 0.38
    for i, (st, mc, mb) in enumerate(rows):
        ax.barh(i + h / 2, mb["rate"] * 100, height=h, color=GREY)
        ax.barh(i - h / 2, mc["rate"] * 100, height=h, color=ACCENT)
        ax.text(mb["rate"] * 100 + 1, i + h / 2, f"{mb['k']}/{mb['n']}", va="center", fontsize=7, color=MUTED)
        ax.text(mc["rate"] * 100 + 1, i - h / 2, f"{mc['k']}/{mc['n']}", va="center", fontsize=7, color=INK)
    ax.set_yticks(range(len(rows)), [r[0].replace("_", " ") for r in rows])
    ax.invert_yaxis()
    ax.set_xlim(0, 112)
    ax.set_xticks([0, 25, 50, 75, 100])
    ax.set_xlabel("leak: percent of items where a private line reached the notes (lower is better)")
    ax.grid(axis="x", color="#e8eaed", linewidth=0.8)
    ax.set_axisbelow(True)
    ax.legend(handles=[plt.Rectangle((0, 0), 1, 1, color=ACCENT), plt.Rectangle((0, 0), 1, 1, color=GREY)],
              labels=["C: ours (no model)", f"{SYSTEM_LABEL[best]} (best baseline overall)"],
              loc="lower left", bbox_to_anchor=(0, 1.0), ncol=2, fontsize=7.5, frameon=False)
    ax.set_title("Leak by case subtype on v2 dev: ours against the best baseline",
                 loc="left", fontsize=10.5, pad=22)
    footnote(fig, f"Source: {src} (246 items, llm none, hold 30 s). Only subtypes with 8 or more items that contain "
                  "private lines. Dev split, so the pipeline may be tuned to it. Small n per row.")
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    save(fig, out, "leak_by_subtype.png")
    return best, rows


# (c) hold seconds vs share of private lines ever committed
def chart_sweep(out):
    src = "bench/results_sweep.json"
    d = load(src)
    pts = []
    for name, sysd in d["systems"].items():
        hold = float(name.split("hold=")[1].rstrip("s"))
        retro_n = sum(it["n_private"] for it in sysd["items"] if it["case_type"] == "retroactive")
        all_n = sum(it["n_private"] for it in sysd["items"] if it["n_private"])
        pts.append((hold, sysd["breakdown"]["retroactive"]["committed_leak_rate"] * 100,
                    sysd["breakdown"]["ALL"]["committed_leak_rate"] * 100, retro_n, all_n))
    pts.sort()
    xs = [p[0] for p in pts]
    fig, ax = plt.subplots(figsize=(6.8, 3.6))
    ax.plot(xs, [p[1] for p in pts], color=ACCENT, linewidth=2, marker="o", markersize=6,
            label=f"retroactive items ({pts[0][3]} private lines)")
    ax.plot(xs, [p[2] for p in pts], color=GREY, linewidth=2, marker="o", markersize=6,
            label=f"all items ({pts[0][4]} private lines)")
    for x, r in zip(xs, [p[1] for p in pts]):
        ax.text(x, r + 3, f"{r:.0f}%", ha="center", fontsize=7.5, color=INK)
    ax.set_xticks(xs)
    ax.set_xlabel("hold time before a line can enter the notes (seconds)")
    ax.set_ylabel("private lines ever committed (%)")
    ax.set_ylim(0, 70)
    ax.grid(axis="y", color="#e8eaed", linewidth=0.8)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, fontsize=8)
    ax.set_title("A longer hold lets \"strike that\" catch a line before it is written", loc="left", fontsize=10.5)
    footnote(fig, f"Source: {src}. Old 47-item synthetic set written with the cue lists in view; "
                  "shows the hold mechanism only, not real-world leak.")
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    save(fig, out, "hold_sweep.png")
    return pts


# (d) published LLM leak rates from other papers
def chart_published(out):
    src = "docs/RESEARCH.md"
    with open(path(src), encoding="utf-8") as f:
        text = f.read()
    for needle in ("| F1 | ConfAIde headline | GPT-4 39%, ChatGPT 57%",
                   "| F9 | PrivacyLens headline | GPT-4 25.68%, Llama-3-70B 38.69%",
                   "Which ConfAIde Tier 4 task is 39%/57%?"):
        assert needle in text, f"RESEARCH.md no longer says: {needle}"
    rows = [("ConfAIde Tier 4 meeting summary, GPT-4", 39.0),
            ("ConfAIde Tier 4 meeting summary, ChatGPT", 57.0),
            ("PrivacyLens agent actions, GPT-4", 25.68),
            ("PrivacyLens agent actions, Llama-3-70B", 38.69)]
    fig, ax = plt.subplots(figsize=(7.2, 2.9))
    ys = range(len(rows))
    ax.barh(list(ys), [r[1] for r in rows], height=0.55, color=GREY)
    for y, (_, v) in zip(ys, rows):
        ax.text(v + 1, y, f"{v:g}%", va="center", fontsize=8, color=INK)
    ax.set_yticks(list(ys), [r[0] for r in rows])
    ax.invert_yaxis()
    ax.set_xlim(0, 70)
    ax.set_xlabel("leak rate reported by the paper (%)")
    ax.grid(axis="x", color="#e8eaed", linewidth=0.8)
    ax.set_axisbelow(True)
    fig.suptitle("Other papers: language models told to keep secrets still leak them", x=0.01, ha="left",
                 fontsize=10.5, fontweight="bold", color=INK)
    footnote(fig, "Other papers' numbers, not ours, and not comparable to OTR-Bench. ConfAIde (arXiv 2310.17884) "
                  "Table 4 with a privacy instruction in the prompt; PrivacyLens helpfulness-adjusted leak with a "
                  f"privacy-enhancing prompt. Checked in {src} (F1, F9, F10, D1).")
    fig.tight_layout(rect=(0, 0.1, 1, 0.93))
    save(fig, out, "published_llm_leak.png")
    return rows


# (e) capability grid from docs/COMPETITORS.md
COLUMNS = ["Consent per\nperson at\nthe audio", "Privacy gate\nbefore notes\nor summary", "Spoken\n\"off the\nrecord\"",
           "Retroactive\n\"strike\nthat\"", "Explains\nwhat was\nwithheld", "Local\nprocessing\nby default",
           "No\nvoiceprints"]
# Each cell: (value, phrase that must appear in COMPETITORS.md). Values: yes, partial (with a short word), no,
# not found (absent from the vendor pages read), unknown (pages say nothing either way).
GRID = [
    ("OTR (this repo)", [
        ("yes", "Consent at the audio track"),
        ("yes", "Hold buffer plus ON/OFF/PENDING state machine"),
        ("yes", "Retroactive removal (\"strike that\", cue and scope handling)"),
        ("partial", "This is not close to solved"),
        ("yes", "Per-item explainability"),
        ("yes*", "Local-only default"),
        ("yes", "Per-person track identity avoids voiceprints"),
    ]),
    ("Meetily", [
        ("not found", "| Meetily | None described [V absence]"),
        ("not found", "None described | Delete files yourself"),
        ("not found", "None described [V absence] | None described"),
        ("manual", "Delete files yourself"),
        ("not found", "No page described a log of what was left out"),
        ("yes", "On device, Whisper or Parakeet"),
        ("yes", "Not in Community edition"),
    ]),
    ("Granola", [
        ("per account", "per account owner"),
        ("not found", "no automatic PII detection"),
        ("not found", "No product I read detects"),
        ("manual", "Manual segment redaction"),
        ("not found", "No page described a log of what was left out"),
        ("no", "Third-party providers, Deepgram and Assembly named"),
        ("unknown", "| Not stated on pages opened | Not found | Manual segment redaction"),
    ]),
    ("Otter", [
        ("not found", "Obligation placed on users"),
        ("not found", "Manual recording pause [U]; bot is visible [U] | Not found"),
        ("not found", "Manual recording pause"),
        ("no", "Trash 30 days [V]"),
        ("not found", "No page described a log of what was left out"),
        ("no", "Audio and transcripts on AWS S3"),
        ("unknown", "the word \"voiceprint\" does not appear"),
    ]),
    ("Fireflies", [
        ("per meeting", "they gate a whole bot join"),
        ("not found", "Pause may be Meet-only per FAQ [V] | Not found"),
        ("pause cmd", "Hey Fireflies, please pause"),
        ("no", "earlier content stays"),
        ("partial", "The closest are Fireflies' pause marker"),
        ("no", "Providers not named"),
        ("no", "voice characteristics"),
    ]),
    ("Fathom", [
        ("per meeting", "Consent emails 24 hours before external meetings"),
        ("not found", "Not found in what I opened | Not found"),
        ("not found", "Not found in what I opened"),
        ("no", "30 day best effort"),
        ("not found", "No page described a log of what was left out"),
        ("no", "Third-party providers named only as OpenAI, Anthropic, Google"),
        ("partial", "Voiceprint only for opted-in iOS users"),
    ]),
    ("Zoom AI Companion", [
        ("host only", "Host turns feature off"),
        ("no", "Teams recap, Zoom and Meet generate notes from the full transcript"),
        ("not found", "no content-aware pause"),
        ("ask host", "Zoom: ask the host"),
        ("not found", "No page described a log of what was left out"),
        ("no", "Zoom models plus third-party providers"),
        ("unknown", "Platform identity (known participants)"),
    ]),
    ("Teams recap", [
        ("organizer", "organizer controls who can record or transcribe"),
        ("no", "Teams recap, Zoom and Meet generate notes from the full transcript"),
        ("not found", "meeting-wide"),
        ("no", "Purview retention and delete"),
        ("not found", "No page described a log of what was left out"),
        ("no", "Azure OpenAI inside the M365 compliance boundary"),
        ("unknown", "attendees can opt out of speaker attribution"),
    ]),
    ("Google Meet notes", [
        ("meeting-wide", "any internal participant can stop it"),
        ("no", "Teams recap, Zoom and Meet generate notes from the full transcript"),
        ("not found", "Stop and restart; no pause"),
        ("no", "Delete the doc"),
        ("not found", "No page described a log of what was left out"),
        ("no", "| Google Meet \"Take notes for me\" | Platform native, Gemini | Google |"),
        ("unknown", "| Platform identity | Stop and restart"),
    ]),
]


def cell_style(v):
    if v.startswith("yes"):
        return ACCENT, "white", "bold"
    if v == "unknown":
        return GREY_PALE, MUTED, "normal"
    if v in ("no", "not found"):
        return "white", MUTED, "normal"
    return ACCENT_PALE, INK, "normal"


def chart_grid(out):
    src = "docs/COMPETITORS.md"
    with open(path(src), encoding="utf-8") as f:
        text = f.read()
    for name, cells in GRID:
        assert len(cells) == len(COLUMNS), name
        for v, phrase in cells:
            assert phrase in text, f"{name}: COMPETITORS.md no longer says: {phrase}"
    n_rows, n_cols = len(GRID), len(COLUMNS)
    fig, ax = plt.subplots(figsize=(9.2, 0.42 * n_rows + 2.2))
    ax.set_xlim(0, n_cols + 1.6)
    ax.set_ylim(n_rows + 1.3, 0)
    ax.axis("off")
    for j, col in enumerate(COLUMNS):
        ax.text(1.6 + j + 0.5, 0.9, col, ha="center", va="bottom", fontsize=7.5, color=INK)
    for i, (name, cells) in enumerate(GRID):
        y = 1.0 + i
        ax.text(0.05, y + 0.5, name, ha="left", va="center", fontsize=8.5, color=INK,
                fontweight="bold" if i == 0 else "normal")
        for j, (v, _) in enumerate(cells):
            bg, fg, wt = cell_style(v)
            ax.add_patch(plt.Rectangle((1.6 + j + 0.04, y + 0.06), 0.92, 0.88, facecolor=bg,
                                       edgecolor="#dadce0", linewidth=0.8))
            ax.text(1.6 + j + 0.5, y + 0.5, v, ha="center", va="center", fontsize=7.5, color=fg, fontweight=wt)
    ax.set_title("What each notetaker documents, per docs/COMPETITORS.md", loc="left", fontsize=11)
    footnote(fig, "Source: docs/COMPETITORS.md (vendor pages read 2026-10-22; nothing was tested). \"not found\" = not "
                  "described on the pages read, which is not proof of absence. \"unknown\" = pages say nothing either "
                  "way. *OTR runs locally by default; the hosted demo routes API traffic through Vercel and a tunnel. "
                  "OTR's \"yes\" means built, not that it works well: see the leak charts.")
    fig.tight_layout(rect=(0, 0.1, 1, 1))
    save(fig, out, "capability_grid.png")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=path("docs", "images", "charts"))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    leak = chart_sealed(a.out)
    print("  v2 sealed item leak:", {k: f"{v:.0%}" for k, v in leak.items()})
    best, rows = chart_subtype(a.out)
    print(f"  v2 dev best baseline: {best}; subtypes with n >= 8: {len(rows)}")
    pts = chart_sweep(a.out)
    print("  sweep (hold s, retro committed %, all committed %):", [(p[0], round(p[1]), round(p[2])) for p in pts])
    chart_published(a.out)
    chart_grid(a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
