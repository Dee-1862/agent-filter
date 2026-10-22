# UI style: avoiding generated-UI tells, copying Google Meet

Check with `python scripts/ui_slop_audit.py` (stdlib only, `--fail` for CI, `--dir` to audit a downloaded copy of the served files). `tests/test_demo.py::test_frontend_passes_ui_slop_audit` runs it.

## Checklist

| Tell | How to detect | Do instead |
|---|---|---|
| Single-side accent border on a card (`border-left` or `border-top` 2px or more, or any non-neutral color) | `border-(top\|right\|bottom\|left)\s*:` with width >= 2px or a colored value; also `border-*-width`, asymmetric `border-width` or `border-color` | No border plus a small leading dot or label, or a 1px neutral border on all four sides, or a tonal background |
| Gradient text, purple to blue gradients | `background-clip: text`, `linear-gradient`, `radial-gradient` | Solid colors; one blue accent `#1a73e8` |
| Glass blur | `backdrop-filter`, `filter: blur` | Opaque surfaces; elevation by surface tone |
| Glowing or colored shadows, hairline plus wide shadow | `box-shadow` with colored rgba, spread rings, large blur | No shadows. A flat 1px neutral border or a different surface tone |
| Emoji or symbol glyphs as icons | code points in U+1F000-1FAFF, U+2600-27BF, HTML entities for them | Inline SVG icons with `currentColor` and an `aria-label` |
| Icon tile above heading, identical 3-up icon card grid, nested cards | markup review; repeated equal cards | Rows and lists, group related items, icon beside the heading |
| Eyebrow label or badge above a heading, tracked uppercase microcopy | `text-transform: uppercase`, `letter-spacing` above .04em, classes `eyebrow`, `pill` | Sentence case, 14px, weights 400 and 500 only |
| Heavy radius on every card, pill outlines | `border-radius` above 16px | 4px buttons, 8px tiles and panels, 50% for circular icon buttons |
| Default Inter or Geist, negative letter spacing, flat hierarchy | `font-family`, `letter-spacing: -` | System stack (Google Sans, Roboto, Segoe UI, Arial), no web font download |
| Decorative motion: bounce, pulse, fade-up, infinite loops | `animation`, `@keyframes`, overshoot `cubic-bezier`, `transition: all` | No animation. Short opacity or transform transitions on panels, covered by `prefers-reduced-motion` |
| Neon dark mode | colored glow on dark surfaces | Meet dark gray `#202124` with `#3c4043` tiles |
| Marketing tagline, hero with tagline and two buttons, filler stats | copy review, `MARKETING` regex in the audit | "Start an instant meeting", "Enter a code or link", "Join now". Never show a number that is not computed |
| Em dashes, "not just X but Y", all-caps strings such as `NOT RECORDING ME` | `U+2014`, `U+2013`, all-caps string regex | Commas, periods, sentence case |

Documented exceptions: the active-speaker ring and focus-visible outline use `outline` on all four sides; a neutral 1px single-side border is allowed as a list divider; a rule can carry `ui-audit-allow: <rule>` (used once, for the wide leave pill and the switch track radius), and an allowed animation also needs `prefers-reduced-motion` in the same file.

## Sources opened (2026)

1. https://www.impeccable.style/slop (side-tab accent, glassmorphism, gradient text, neon glow, eyebrow, icon tile, identical card grid, pulsing dots, bounce easing, em dash)
2. https://capitalandcompute.net/blog/fix-ai-slop-design/ (first and second wave defaults, card kit, reflexive glass, motion on everything, filler copy)
3. https://cdn.jsdelivr.net/npm/@hegemonart/get-design-done@1.60.4/reference/anti-patterns.md (BAN-01 side-stripe regex, gradient text regex, bounce easing, `transition: all`)
4. https://www.superdesign.dev/blog/why-ai-design-looks-generic (indigo `#6366F1`, purple gradient, rounded everything, soft shadows, centered hero, 3-card row, `border-left` cards, glass, eyebrow badge)
5. https://www.bitdoze.com/best-ai-skills-for-web-design/ (Inter default, purple to blue hero, card in card, icon tiles, gray on color, bounce easing)
6. https://www.lovart.ai/de/blog/how-to-detect-ai-generated-content-design (generic output; mostly about images, little CSS signal)
7. https://workspaceupdates.googleblog.com/2024/06/updated-design-for-meeting-controls-google-meet.html (Meet Material 3 bottom controls, dynamic shapes, vivid end call)
8. https://9to5google.com/2024/06/11/google-meet-material-3/ (same change, web and hardware scope)

Search results only (not opened): 9to5google Material 3 Expressive piece, originality.ai and uxplanet detection posts, a UK government page on em dashes and emoji.

Not confirmed by the sources: that glassmorphism and emoji icons are tells beyond Impeccable and superdesign (single-source); any numeric radius limit (the 16px threshold is our choice); exact Meet colors, sizes and side panel styling (no official spec found; values below come from our own reading of the product, not a source).

## Google Meet design language (what we copy)

- Home: white page, system font stack, left column heading with plain buttons ("Start an instant meeting", "Enter a code or link", "Join now"), right column a plain tile preview. Flat surfaces, 8px grid, primary blue `#1a73e8`. A dark variant follows `prefers-color-scheme`.
- In call: dark `#202124` stage filling the window, tiles `#3c4043` with 8px radius and 8px gaps, participant name bottom-left, mic state icon top-right.
- Bottom bar: meeting time and name at left, centered circular icon-only buttons (microphone, camera, captions) and a wide red `#ea4335` leave pill, small icon buttons at right (People, Meeting details, Off The Record). Names live in `aria-label` and `title`.
- One right-hand white side panel at a time. Off The Record panel: one-line status, notes switch, captions of your approved lines, two plain links (What was kept out, How it decides) that open inside the panel with a back arrow, and a "Jump to latest" chip only when scrolled up.
- Active speaker: 2px outline on all four sides. No colored top or left strips. Elevation by surface tone, never by shadow glow.

## Status

See the audit output for current counts. Not verified: real WebRTC audio and camera, any browser besides headless Edge, narrow phone layout beyond CSS review.
