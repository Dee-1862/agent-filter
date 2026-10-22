"""OTR-Bench v2 builders (real QMSum/AMI/ICSI/committee background + LLM-authored insertions).

See bench/data_v2/README.md. Pipeline:
  python -m bench.v2.select_windows   # raw QMSum -> work/windows.json + per-author briefs
  (author agents write work/authored/<author>_*.json)
  python -m bench.v2.assemble         # -> data_v2/dev/*.jsonl, data_v2/sealed/*.jsonl, manifests, checks
"""
