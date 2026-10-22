"""Draw red highlight outlines on the README showcase screenshots, around what the reader should look at.

  python scripts/annotate_showcase.py

Writes <name>-marked.png next to each source image. Coordinates are for the 1280x800 captures from
experiments/showcase.py; rerun this after a new recording if the layout changes.
"""
from pathlib import Path

from PIL import Image, ImageDraw

DIR = Path(__file__).resolve().parents[1] / "docs" / "images" / "showcase"
RED = (234, 67, 53)

# image -> list of (left, top, right, bottom) boxes
MARKS = {
    "02-explicit-off-the-record-lance.png": [(945, 500, 1108, 521)],
    "03-reaction-kept-out-too-reddy.png": [(945, 469, 1108, 521)],
    "04-strike-that-retraction-lance.png": [(945, 469, 1082, 521)],
    "05-sensitive-lines-kept-out-not-tuff.png": [(945, 469, 1108, 521)],
    "07-removed-by-you-lance.png": [(928, 656, 1230, 670)],
    "09-insights-reddy.png": [(930, 70, 1258, 146), (928, 160, 1258, 262)],
    "11-why-kept-out-not-tuff.png": [(930, 172, 1256, 196), (945, 416, 1239, 648)],
}


def main() -> None:
    for name, boxes in MARKS.items():
        src = DIR / name
        if not src.exists():
            print("missing", name)
            continue
        img = Image.open(src).convert("RGB")
        d = ImageDraw.Draw(img)
        for (l, t, r, b) in boxes:
            pad = 7
            d.rounded_rectangle((l - pad, t - pad, r + pad, b + pad), radius=10, outline=RED, width=4)
        out = src.with_name(src.stem + "-marked.png")
        img.save(out, optimize=True)
        print("wrote", out.name)


if __name__ == "__main__":
    main()
