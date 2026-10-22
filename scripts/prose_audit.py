#!/usr/bin/env python3
"""Scan README.md and docs/*.md for common tells of AI-written technical prose.

Usage:
    python scripts/prose_audit.py            # counts per tell, per file
    python scripts/prose_audit.py -v         # also print file:line for each hit
    python scripts/prose_audit.py FILE...    # scan specific files

Fenced code blocks are skipped. Table rows are skipped for the dash check
only when the dash sits between digits (a numeric range).
Skipped entirely: docs/CHANGES.md, docs/LESSONS_LEARNED.md, docs/RESEARCH.md
(append-only logs or owned elsewhere), unless named on the command line.

Verified tells (sources read in Oct 2026; these are weak signals, not proof,
and one instance in a document is normal):

  1. Em dashes (and en dashes used as breaks). Pangram: 17 vs 2 per 10k
     words, about 10x. Wikipedia's field guide lists it but marks it a
     fading indicator after late 2025 model updates (Yaps, 2026, says the
     same). Still the most checkable one.
  2. "Not just X, but Y" / "not only ... but also" negative parallelism.
     Pangram: about 3x. Wikipedia, Beutler Ink, Weichart list it.
  3. Rule of three: reflexive triplets of near-synonyms. Pangram: about 4x.
  4. Stock vocabulary: delve (Pangram: 45x), tapestry, pivotal, crucial,
     robust, seamless, leverage (verb), comprehensive, landscape,
     underscore, showcase, intricate, streamline, foster, realm,
     cornerstone, testament. Wikipedia, Weichart, Beutler Ink.
  5. Stock phrases: "it is worth noting", "it's important to note",
     "in today's", "in the ever-evolving". Weichart, Yaps.
  6. Formatting overkill: bold-lead bullets ("- **Term:** ..."), emoji in
     headings, heavy bold, bullets where prose fits. Pangram: bullet lists
     9x, markdown 12x; Beutler Ink; Wikipedia.
  7. Title Case on every heading (Wikipedia lists title-case headings).
  8. Inflated significance: "stands as a testament", "pivotal moment",
     "game-changer", "plays a crucial role". Wikipedia, Weichart.
  9. Vague attribution: "experts say", "research shows", "studies suggest".
     Wikipedia, Weichart.
 10. Summarizing closers: "In conclusion", "Overall,", "In summary".
     Beutler Ink, Weichart, Yaps.
 11. Promotional tone: "boasts", "vibrant", "nestled", "rich", "powerful".
     Wikipedia, Weichart.
 12. Copula avoidance ("serves as", "stands as") and trailing "-ing"
     clauses ("..., ensuring a seamless experience"). Wikipedia, Weichart.

Sources:
  - https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing (read 2026)
  - https://www.pangram.com/signs-of-ai-writing (per-10k-word figures)
  - https://www.beutlerink.com/blog/how-to-spot-ai-writing (Jan, based on
    the Wikipedia guide)
  - https://alexanderweichart.de/7_Agent/skills/write-in-my-voice/references/anti-ai-writing
  - https://www.yaps.ai/nl/blog/how-to-detect-ai-writing (Jun/Sep 2026;
    notes that none of these is proof)
  - https://flowingdata.com/?p=80144 and
    https://pasqualepillitteri.it/en/news/403/spot-ai-generated-text-detector-checker
    (seen in search results only, not read in full)
"""
import argparse
import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP = {"CHANGES.md", "LESSONS_LEARNED.md", "RESEARCH.md"}

WORDS = (r"delve|tapestry|pivotal|crucial|robust|seamless(?:ly)?|leverag(?:e|es|ed|ing)|"
         r"comprehensive|landscape|underscor(?:e|es|ed|ing)|showcas(?:e|es|ed|ing)|"
         r"intricate|streamlin(?:e|es|ed|ing)|foster(?:s|ed|ing)?|realm|cornerstone|"
         r"testament|holistic|game-changer|cutting-edge|state-of-the-art|"
         r"paradigm|synerg(?:y|ies)|empower(?:s|ed|ing)?")

TELLS = [
    ("em/en dash", re.compile("[—–]")),
    ("not just X but Y", re.compile(r"\bnot (?:just|only|merely|simply)\b.{0,80}\b(?:but|it's|it is)\b", re.I)),
    ("stock words", re.compile(r"\b(?:%s)\b" % WORDS, re.I)),
    ("stock phrases", re.compile(r"worth noting|important to note|in today's|ever-evolving|it should be noted|"
                                 r"at the end of the day|when it comes to", re.I)),
    ("bold-lead bullet", re.compile(r"^\s*(?:[-*]|\d+\.)\s+\*\*[^*]+\*\*\s*[:\-.]")),
    ("emoji", re.compile("[\U0001F300-\U0001FAFF☀-➿✅❌]")),
    ("inflated significance", re.compile(r"testament to|pivotal|game-chang|plays? a (?:crucial|key|vital) role|"
                                         r"watershed|lasting impact|paving the way|cannot be overstated", re.I)),
    ("vague attribution", re.compile(r"\b(?:experts|studies|research|critics|observers) (?:say|show|suggest|argue|agree|have)\b", re.I)),
    ("summarizing closer", re.compile(r"^\s*(?:in conclusion|in summary|overall|ultimately|to summarize)\b", re.I)),
    ("promotional", re.compile(r"\b(?:boasts?|vibrant|nestled|breathtaking|world-class|powerful|effortless(?:ly)?|"
                               r"blazing|lightning-fast|best-in-class)\b", re.I)),
    ("serves/stands as", re.compile(r"\b(?:serves|stands|acts) as\b", re.I)),
    ("trailing -ing clause", re.compile(r",\s+(?:ensuring|highlighting|underscoring|showcasing|reflecting|enabling)\b", re.I)),
]
TRIPLE = re.compile(r"\b[\w-]+, [\w-]+,? (?:and|or) [\w-]+\b")  # informational only, not counted


def title_case_heading(line):
    m = re.match(r"^#{1,6}\s+(.*)$", line)
    if not m:
        return False
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z'-]*", m.group(1)) if len(w) > 3]
    return len(words) >= 3 and all(w[0].isupper() for w in words)


def scan(path):
    hits = {}
    in_code = False
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            s = line.rstrip("\n")
            if s.lstrip().startswith("```"):
                in_code = not in_code
                continue
            if in_code:
                continue
            for name, rx in TELLS:
                if rx.search(s):
                    if name == "em/en dash" and s.lstrip().startswith("|") and re.search(r"\d\s*[–—]\s*\d", s):
                        continue
                    hits.setdefault(name, []).append(n)
            if title_case_heading(s):
                hits.setdefault("title-case heading", []).append(n)
    return hits


def targets(args):
    if args:
        return args
    files = [os.path.join(ROOT, "README.md")]
    files += sorted(glob.glob(os.path.join(ROOT, "docs", "*.md")))
    return [f for f in files if os.path.basename(f) not in SKIP and os.path.exists(f)]


def main():
    doc = __doc__ or ""
    ap = argparse.ArgumentParser(description=doc, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*")
    ap.add_argument("-v", "--verbose", action="store_true", help="print file:line for every hit")
    a = ap.parse_args()
    totals = {}
    for p in targets(a.files):
        rel = os.path.relpath(p, ROOT)
        hits = scan(p)
        if not hits:
            continue
        print(rel)
        for name, lines in sorted(hits.items()):
            totals[name] = totals.get(name, 0) + len(lines)
            print("  %-22s %3d" % (name, len(lines)))
            if a.verbose:
                for n in lines:
                    print("    %s:%d" % (rel, n))
    print("TOTAL")
    for name, c in sorted(totals.items()):
        print("  %-22s %3d" % (name, c))
    print("  %-22s %3d" % ("ALL", sum(totals.values())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
