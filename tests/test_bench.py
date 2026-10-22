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
