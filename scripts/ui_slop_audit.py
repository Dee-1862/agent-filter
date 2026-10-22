#!/usr/bin/env python
"""Audit demo/static/*.css|html|js for visual and copy tells of generated UI (see docs/UI_STYLE.md).

Stdlib only. Prints file:line findings and counts per rule.

    python scripts/ui_slop_audit.py                 # audit demo/static
    python scripts/ui_slop_audit.py --dir some/dir  # audit a downloaded copy of the served files
    python scripts/ui_slop_audit.py --fail          # exit 1 when anything is found

Documented exceptions (not findings):
  * focus-visible outlines and the active-speaker outline: `outline` is never flagged, and an all-sides
    `border` / `border-color` is never flagged. Only single-side or asymmetric borders are.
  * a neutral 1px single-side border (divider between list rows) is allowed.
  * anything marked with a comment `ui-audit-allow: <rule>` on the same line or the two lines before it,
    for example a pulse on the single live-recording indicator. An allowed animation is only accepted when the
    same file also contains `prefers-reduced-motion`; otherwise it is still reported.
Vendored files (livekit-client.*) are skipped. categories.js is generated from demo/categories.py and is scanned.
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DIR = ROOT / "demo" / "static"
EXTS = {".css", ".html", ".js"}

EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF☀-➿⭐⭕⬛⬜️‍⌚⌛⏩-⏿]"
)
EMOJI_ENTITY = re.compile(r"&#(?:x([0-9a-fA-F]+)|(\d+));")
DASH = re.compile("[–—]|&mdash;|&ndash;|\\\\u201[34]", re.I)
MARKETING = re.compile(
    r"your voice, your choice|decide what gets noted|supercharge|seamless|effortless|elevate your|unlock|"
    r"empower|revolutioni[sz]e|next-gen|world-class|enterprise-grade|\bnot just\b|reimagine|game-chang",
    re.I,
)
ALLCAPS_STRING = re.compile(r"""(["'>])([A-Z][A-Z ]{7,})(["'<])""")
BAD_CLASS = re.compile(r"""class(?:Name)?\s*=\s*["'][^"']*\b(eyebrow|kicker|glow|glass|gradient|hero-badge)\b""", re.I)
ANIM_NAME = re.compile(r"bounce|pulse|fade|slide|float|glow|shimmer|ring|wiggle|elastic|spin|blink|ping", re.I)

NEUTRAL_VAR = re.compile(r"var\(--(?:line|border|divider|outline|panel-line|v-line|hairline)[\w-]*\)")


def hex_is_neutral(h: str) -> bool:
    h = h.lstrip("#")
    if len(h) in (3, 4):
        h = "".join(c * 2 for c in h[:3])
    if len(h) < 6:
        return False
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return max(r, g, b) - min(r, g, b) <= 24


def color_is_neutral(value: str) -> bool:
    """True when every color in the value is a gray, transparent, black, white or a neutral token."""
    v = value.lower()
    if NEUTRAL_VAR.search(v) or "transparent" in v or "currentcolor" in v:
        return True
    colors = re.findall(r"#[0-9a-f]{3,8}\b", v)
    for m in re.finditer(r"rgba?\(\s*(\d+)[\s,]+(\d+)[\s,]+(\d+)", v):
        r, g, b = (int(x) for x in m.groups())
        colors.append("#%02x%02x%02x" % (r, g, b))
    if re.search(r"var\(--(?:blue|green|red|amber|yellow|accent|ok|out|wait|c|v-ok|v-out|v-wait|v-accent)[\w-]*\)", v):
        return False
    if not colors:
        return not re.search(r"\b(red|green|blue|orange|yellow|purple|pink|teal|cyan)\b", v)
    return all(hex_is_neutral(c) for c in colors)


def top_tokens(value: str) -> list[str]:
    """Split a CSS value on whitespace outside parentheses."""
    out, depth, cur = [], 0, ""
    for ch in value:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch.isspace() and depth == 0:
            if cur:
                out.append(cur)
            cur = ""
        else:
            cur += ch
    if cur:
        out.append(cur)
    return out


def line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def allowed(lines: list[str], lineno: int, rule: str) -> bool:
    for i in range(max(0, lineno - 3), lineno):
        if "ui-audit-allow" in lines[i] and rule in lines[i]:
            return True
    return False


class Audit:
    def __init__(self):
        self.findings: list[tuple[str, int, str, str]] = []
        self.allowed: list[tuple[str, int, str]] = []

    def add(self, path, lineno, rule, snippet, lines, file_text=""):
        if allowed(lines, lineno, rule):
            if rule == "animation" and "prefers-reduced-motion" not in file_text:
                pass  # an animation exception needs a reduced-motion rule in the same file
            else:
                self.allowed.append((path, lineno, rule))
                return
        safe = snippet.strip()[:110].encode("ascii", "backslashreplace").decode("ascii")
        self.findings.append((path, lineno, rule, safe))


def strip_comments_keep_lines(css: str) -> str:
    return re.sub(r"/\*.*?\*/", lambda m: re.sub(r"[^\n]", " ", m.group(0)), css, flags=re.S)


def audit_css_block(a: Audit, name: str, text: str, lines: list[str], css: str, base_offset: int):
    """css is the (comment-stripped) CSS; base_offset maps it back into the file text."""
    file_text = text
    for blk in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        selector = blk.group(1).strip()
        body = blk.group(2)
        body_start = base_offset + blk.start(2)
        decls = []
        for d in re.finditer(r"([\w-]+)\s*:\s*([^;]+);?", body):
            decls.append((d.group(1).lower(), d.group(2).strip(), line_of(text, body_start + d.start())))
        props = {p: v for p, v, _ in decls}
        for prop, value, ln in decls:
            snippet = f"{selector[:50]} {{ {prop}: {value} }}"
            m = re.fullmatch(r"border-(top|right|bottom|left)", prop)
            if m:
                width = re.search(r"(\d+(?:\.\d+)?)px", value)
                w = float(width.group(1)) if width else 1.0
                if value.strip() not in ("0", "none") and (w >= 2 or not color_is_neutral(value)):
                    a.add(name, ln, "side-border", snippet, lines, file_text)
                elif value.strip() not in ("0", "none"):
                    pass  # neutral 1px divider
            if re.fullmatch(r"border-(top|right|bottom|left)-color", prop) and not color_is_neutral(value):
                a.add(name, ln, "side-border", snippet, lines, file_text)
            if re.fullmatch(r"border-(top|right|bottom|left)-width", prop):
                num = re.search(r"[\d.]+", value)
                if num and float(num.group(0)) >= 2:
                    a.add(name, ln, "side-border", snippet, lines, file_text)
            if prop == "border-width" and len(set(top_tokens(value))) > 1:
                a.add(name, ln, "border-asymmetry", snippet, lines, file_text)
            if prop == "border-color" and len(set(top_tokens(value))) > 1:
                a.add(name, ln, "border-asymmetry", snippet, lines, file_text)
            if "gradient" in value and prop in ("background", "background-image", "border-image", "color", "mask-image"):
                a.add(name, ln, "gradient", snippet, lines, file_text)
            if prop in ("background-clip", "-webkit-background-clip") and "text" in value:
                a.add(name, ln, "gradient-text", snippet, lines, file_text)
            if prop == "-webkit-text-fill-color" and "transparent" in value:
                a.add(name, ln, "gradient-text", snippet, lines, file_text)
            if prop in ("backdrop-filter", "-webkit-backdrop-filter") or (prop == "filter" and "blur" in value):
                a.add(name, ln, "blur-glass", snippet, lines, file_text)
            if prop == "box-shadow" and value.strip() != "none":
                neutral_ring = re.fullmatch(r"(inset\s+)?0 0 0 1px [^,]+", value.strip()) and color_is_neutral(value)
                if not neutral_ring:
                    kind = "glow-shadow" if not color_is_neutral(value) or "var(--c" in value else "shadow"
                    a.add(name, ln, kind, snippet, lines, file_text)
            if prop == "text-transform" and "uppercase" in value:
                a.add(name, ln, "uppercase", snippet, lines, file_text)
            if prop == "letter-spacing":
                num = re.search(r"-?\d*\.?\d+", value)
                n = float(num.group(0)) if num else 0.0
                unit_px = "px" in value
                if n < 0 or (n > 0.5 if unit_px else n > 0.04):
                    a.add(name, ln, "letter-spacing", snippet, lines, file_text)
            if prop in ("animation", "animation-name"):
                if not re.fullmatch(r"(none|0)(\s*!important)?", value.strip()):
                    a.add(name, ln, "animation", snippet, lines, file_text)
            if prop == "transition" and re.match(r"all\b", value):
                a.add(name, ln, "transition-all", snippet, lines, file_text)
            if "cubic-bezier" in value:
                nums = [float(x) for x in re.findall(r"-?\d*\.?\d+", value.split("cubic-bezier", 1)[1])[:4]]
                if any(x < 0 or x > 1 for x in nums[:4]):
                    a.add(name, ln, "animation", snippet, lines, file_text)
            if prop == "border-radius":
                for token in re.findall(r"(\d+(?:\.\d+)?)(px|rem|em)", value):
                    n = float(token[0]) * (16 if token[1] != "px" else 1)
                    if n > 16 and n < 500:
                        a.add(name, ln, "heavy-radius", snippet, lines, file_text)
                        break
                if re.search(r"\b(999|9999)", value):
                    a.add(name, ln, "heavy-radius", snippet, lines, file_text)
            if prop == "font-family" and re.search(r"\binter\b|\bgeist\b", value, re.I):
                a.add(name, ln, "default-font", snippet, lines, file_text)
        # border shorthand with an inline sides mix, e.g. border-style: solid none none none
        if "border-style" in props and len(set(props["border-style"].split())) > 1 and "none" in props["border-style"]:
            a.add(name, 0, "border-asymmetry", f"{selector[:50]} border-style: {props['border-style']}", lines, file_text)
    for kf in re.finditer(r"@keyframes\s+([\w-]+)", css):
        a.add(name, line_of(text, base_offset + kf.start()), "animation", "@keyframes " + kf.group(1), lines, file_text)


def audit_text_rules(a: Audit, name: str, text: str, lines: list[str], is_vendor_css: bool = False):
    for i, ln in enumerate(lines, 1):
        for m in EMOJI.finditer(ln):
            a.add(name, i, "emoji", f"U+{ord(m.group(0)):04X} in: {ln}", lines, text)
            break
        for m in EMOJI_ENTITY.finditer(ln):
            cp = int(m.group(1), 16) if m.group(1) else int(m.group(2))
            if EMOJI.match(chr(cp)):
                a.add(name, i, "emoji", f"entity {m.group(0)} in: {ln}", lines, text)
        if DASH.search(ln):
            a.add(name, i, "dash", ln, lines, text)
        if MARKETING.search(ln):
            a.add(name, i, "marketing-copy", ln, lines, text)
        caps = ALLCAPS_STRING.search(ln)
        if caps and name.endswith((".js", ".html")) and caps.group(2).strip() not in ("INPUT", "TEXTAREA", "SELECT", "BUTTON"):
            a.add(name, i, "allcaps-copy", ln, lines, text)
        if name.endswith((".js", ".html")) and BAD_CLASS.search(ln):
            a.add(name, i, "slop-class", ln, lines, text)
        if re.search(r"""\.style\.(border\w*|boxShadow|backdropFilter|background)\b""", ln):
            a.add(name, i, "inline-style-js", ln, lines, text)
        if re.search(r"""\.animate\(|classList\.(add|toggle)\(\s*["'](pulse|bounce|fade|shake|glow)""", ln):
            a.add(name, i, "animation", ln, lines, text)
        if re.search(r"""style\s*=\s*["']""", ln) and name.endswith(".html"):
            if "live.html" in name:
                a.add(name, i, "inline-style-attr", ln, lines, text)


def audit_file(a: Audit, path: Path, display: str):
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    audit_text_rules(a, display, text, lines)
    if path.suffix == ".css":
        css = strip_comments_keep_lines(text)
        audit_css_block(a, display, text, lines, css, 0)
    elif path.suffix == ".html":
        for sm in re.finditer(r"<style[^>]*>(.*?)</style>", text, re.S):
            css = strip_comments_keep_lines(sm.group(1))
            audit_css_block(a, display, text, lines, css, sm.start(1))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", default=str(DEFAULT_DIR), help="directory holding the css/html/js files")
    ap.add_argument("--fail", action="store_true", help="exit 1 if there is any finding")
    ap.add_argument("--quiet", action="store_true", help="print only the summary")
    args = ap.parse_args(argv)
    base = Path(args.dir)
    a = Audit()
    files = sorted(p for p in base.iterdir() if p.suffix in EXTS and not p.name.startswith("livekit"))
    if not files:
        print(f"no css/html/js files in {base}", file=sys.stderr)
        return 2
    for p in files:
        audit_file(a, p, p.name)
    if not args.quiet:
        for path, ln, rule, snip in sorted(a.findings):
            print(f"{path}:{ln}: [{rule}] {snip}")
    counts = Counter(rule for _, _, rule, _ in a.findings)
    print("\nsummary")
    for rule, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  {rule:18} {n}")
    per_file = Counter(path for path, _, _, _ in a.findings)
    for path, n in sorted(per_file.items()):
        print(f"  file {path:18} {n}")
    print(f"  allowed by documented exception: {len(a.allowed)}")
    print(f"TOTAL findings: {len(a.findings)}")
    return 1 if (args.fail and a.findings) else 0


if __name__ == "__main__":
    sys.exit(main())
