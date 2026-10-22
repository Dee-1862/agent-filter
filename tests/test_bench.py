import json
from pathlib import Path

import pytest

from bench import metrics, systems
from bench.run_eval import BENCH, load_items, evaluate
from otr.types import Segment

CASES = {"explicit_start_end", "explicit_start_implicit_end", "retroactive", "implicit", "false_alarm"}


@pytest.fixture(scope="module")
def items():
    return load_items(BENCH)


def test_schema(items):
    assert len(items) >= 40
    assert len({i["id"] for i in items}) == len(items)
    for it in items:
        assert it["source"] and it["case_type"] in CASES
        ids = [s["id"] for s in it["segments"]]
        assert len(ids) == len(set(ids)) and 8 <= len(ids) <= 20, it["id"]
        for s in it["segments"]:
            Segment(**s)
            assert s["t_end"] > s["t_start"]
        assert set(it["private_ids"]) <= set(ids) and set(it["public_ids"]) <= set(ids)
        assert not set(it["private_ids"]) & set(it["public_ids"])
        assert it["public_ids"] and it["public_facts"]
        if it["case_type"] == "false_alarm":
            assert not it["private_ids"]
        else:
            assert it["private_ids"]
        pub_text = " ".join(s["text"] for s in it["segments"] if s["id"] in it["public_ids"]).lower()
        assert all(f.lower() in pub_text for f in it["public_facts"])


def test_all_case_types_covered(items):
    assert {i["case_type"] for i in items} == CASES


def _seg(i, text="x"):
    return Segment(id=i, speaker="a", text=text, t_start=0, t_end=1)


def test_metrics_math():
    item = {"id": "t", "case_type": "implicit", "private_ids": ["a", "b"],
            "public_ids": ["c", "d"], "public_facts": ["alpha beta", "gamma"]}
    r = metrics.score_item(item, [_seg("a"), _seg("c", "Alpha Beta here")])
    assert (r["n_leaked"], r["n_missing"], r["n_facts_found"]) == (1, 1, 1)
    agg = metrics.aggregate([r])
    assert agg["leak_rate"] == 0.5 and agg["over_redaction"] == 0.5
    assert agg["summary_usefulness"] == 0.5 and agg["item_leak_rate"] == 1.0


def test_metrics_no_private():
    item = {"id": "t", "case_type": "false_alarm", "private_ids": [], "public_ids": ["c"], "public_facts": []}
    agg = metrics.aggregate([metrics.score_item(item, [_seg("c")])])
    assert agg["leak_rate"] is None and agg["over_redaction"] == 0.0


def test_system_a_smoke(items):
    res = evaluate(systems.run_A, items)
    b = res["breakdown"]
    assert b["ALL"]["n_items"] == len(items)
    assert b["explicit_start_end"]["leak_rate"] < 0.2          # explicit cues are A's home turf
    assert b["false_alarm"]["over_redaction"] > 0              # naive keywords misfire on false alarms
    assert b["implicit"]["leak_rate"] is not None


def test_system_b_stub_runs(items):
    notes = systems.run_B(items[0])
    assert all(isinstance(s, Segment) for s in notes)
    assert systems.label("B", None) == "B-stub"


def test_system_b_llm_parsing(items):
    it = items[0]
    keep = [it["segments"][0]["id"]]

    class Fake:
        def complete(self, prompt):
            return "sure: " + json.dumps({"keep": keep})

    assert [s.id for s in systems.run_B(it, Fake())] == keep


def test_system_c_runs_streaming_and_hold_matters_for_committed_leaks(items):
    """C is replayed as a live stream (now = t_end, clock ticked past the end). Final-notes leaks
    do not depend on hold, but text committed before a retroactive cue arrives does."""
    ret = [i for i in items if i["case_type"] == "retroactive"]
    short = evaluate(systems.run_C, ret, hold_seconds=0.0)["breakdown"]["ALL"]
    long_ = evaluate(systems.run_C, ret, hold_seconds=30.0)["breakdown"]["ALL"]
    assert long_["committed_leak_rate"] < short["committed_leak_rate"]
    assert long_["leak_rate"] <= long_["committed_leak_rate"]
    notes = systems.run_C(ret[0], None, hold_seconds=30.0)
    assert hasattr(notes, "ever_committed_ids")


def test_noisy_asr_items_present(items):
    noisy = [i for i in items if any(k in s["text"] for s in i["segments"]
                                     for k in ("da record", "of the record", "awf the record", "strike dat", "scratch dat"))]
    assert len(noisy) >= 5 and all(i["source"] == "synthetic" for i in noisy)


# ----------------------------------------------------------------------------- held-out set + stats
HELD = Path(__file__).resolve().parent.parent / "bench" / "heldout"
HELD_CASES = CASES | {"public"}


def _held(name):
    return load_items(HELD / name)


@pytest.mark.parametrize("name", ["heldout.jsonl", "heldout_noisy.jsonl"])
def test_heldout_schema(name):
    items = _held(name)
    assert len(items) == 36
    assert len({i["id"] for i in items}) == 36
    from collections import Counter
    assert set(Counter(i["case_type"] for i in items).values()) == {6}
    assert {i["case_type"] for i in items} == HELD_CASES
    for it in items:
        assert it["source"].startswith("synthetic-heldout")
        ids = [s["id"] for s in it["segments"]]
        assert len(ids) == len(set(ids)) and 8 <= len(ids) <= 14, it["id"]
        for s in it["segments"]:
            Segment(**s)
            assert s["t_end"] > s["t_start"]
        assert set(it["private_ids"]) <= set(ids) and set(it["public_ids"]) <= set(ids)
        assert set(it["cue_ids"]) <= set(ids)
        assert not set(it["private_ids"]) & set(it["public_ids"])
        assert it["public_ids"] and it["public_facts"]
        if it["case_type"] in ("explicit_start_end", "explicit_start_implicit_end", "implicit"):
            assert it["private_ids"]
        if it["case_type"] in ("false_alarm", "public"):
            assert not it["private_ids"]
        pub_text = " ".join(s["text"] for s in it["segments"] if s["id"] in it["public_ids"]).lower()
        assert all(f.lower() in pub_text for f in it["public_facts"])


def test_heldout_noisy_only_touches_cue_lines():
    a, b = _held("heldout.jsonl"), _held("heldout_noisy.jsonl")
    changed = 0
    for x, y in zip(a, b):
        assert y["id"] == x["id"] + "-n" and len(x["segments"]) == len(y["segments"])
        cue = set(x["cue_ids"])
        for s, t in zip(x["segments"], y["segments"]):
            if s["id"] not in cue:
                assert s["text"] == t["text"]
            elif s["text"] != t["text"]:
                changed += 1
                assert t["text"] == t["text"].lower()
    assert changed >= 25


def test_heldout_build_is_deterministic():
    from bench.heldout import build_heldout as bh
    items = bh.build()
    assert items == _held("heldout.jsonl")
    assert bh.noisy(items) == _held("heldout_noisy.jsonl")


def test_wilson_matches_research_table():
    # docs/RESEARCH.md section 6 (n = 40)
    for k, lo, hi in [(0, 0.0, 0.088), (2, 0.014, 0.165), (5, 0.055, 0.261), (6, 0.071, 0.291),
                      (12, 0.181, 0.454), (20, 0.352, 0.648)]:
        l, h = metrics.wilson(k, 40)
        assert abs(l - lo) < 0.002 and abs(h - hi) < 0.002, k
    assert metrics.wilson(0, 0) == (None, None)


def test_mcnemar_worked_example():
    # B 12/40 vs C 5/40; b = 9, c = 2, both = 3, neither = 26 -> p = 0.0654, risk diff 17.5 points
    assert abs(metrics.mcnemar_exact(9, 2) - 0.0654) < 5e-5
    assert metrics.mcnemar_exact(0, 0) == 1.0 and metrics.mcnemar_exact(5, 5) == 1.0
    lo, hi = metrics.clopper_pearson(9, 11)
    assert abs(lo - 0.482) < 0.002 and abs(hi - 0.977) < 0.002
    c_ids = {0, 1, 2} | {12, 13}                                      # both leak on 0,1,2; C-only on 12,13
    rows_b = [{"id": i, "leak": i in set(range(3, 12)) | {0, 1, 2}} for i in range(40)]
    rows_c = [{"id": i, "leak": i in c_ids} for i in range(40)]
    r = metrics.paired(rows_b, rows_c)
    assert (r["b"], r["c"], r["both"], r["neither"], r["n"]) == (9, 2, 3, 26, 40)
    assert abs(r["p"] - 0.0654) < 5e-5 and abs(r["risk_diff"] - 0.175) < 1e-9


def test_item_level_confaide_metrics():
    item = {"id": "t", "case_type": "implicit", "private_ids": ["a"], "public_ids": ["c", "d"], "public_facts": []}
    agg = metrics.aggregate([metrics.score_item(item, [_seg("a"), _seg("c")])])
    assert agg["Leak"]["k"] == 1 and agg["Omit-Public"]["k"] == 1 and agg["Leak-or-Omit"]["k"] == 1
    assert agg["descriptive_only"] is True


def test_b_and_bplus_modes_with_fake_llm():
    it = _held("heldout.jsonl")[0]
    sid = it["segments"][0]["id"]

    class FakeBplus:
        def complete(self, prompt):
            if "Judge ONLY" in prompt:
                return json.dumps({"decision": "drop"})
            return json.dumps({"segments": [{"id": sid, "decision": "drop"}]})

    n = len(it["segments"])
    assert [s.id for s in systems.run_Bplus(it, FakeBplus())] == [s["id"] for s in it["segments"][1:]]
    assert systems.run_Bplus(it, FakeBplus(), mode="causal") == []
    assert systems.label("B+", None) == "B+-stub" and systems.label("B+/causal", None) == "B+-stub/causal"
    assert len(systems.run_B(it, None, mode="causal", hold_seconds=0)) <= n


def test_causal_window_hides_future():
    item = {"segments": [{"id": f"s{i}", "speaker": "a", "text": "x", "t_start": 10 * i, "t_end": 10 * i + 5}
                         for i in range(5)]}
    segs = systems.to_segments(item)
    assert [s.id for s in systems._visible(segs, 1, 0.0)] == ["s0", "s1"]
    assert [s.id for s in systems._visible(segs, 1, 10.0)] == ["s0", "s1", "s2"]


def test_c_exposes_stage_log_on_heldout():
    it = _held("heldout.jsonl")[0]
    row = metrics.score_item(it, systems.run_C(it, None, hold_seconds=30.0))
    assert "stages" in row and set(row["stages"]) == {"private_leaked", "private_blocked", "public_lost"}
