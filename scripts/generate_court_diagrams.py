"""Draw the four half-court diagrams used by the image-answer example question.

Each diagram is the same half court with exactly one line drawn in red. Kept as
a script so the assets are reproducible rather than opaque binaries: re-run it
to regenerate, and to add a fifth line as a fifth option.
"""

from pathlib import Path

from PIL import Image, ImageDraw

W, H = 480, 440
COURT = "#f2e4cc"
LINE = "#4a4a4a"
HIGHLIGHT = "#d1344a"
PAD = 30

# Half court, viewed from above: baseline at the bottom, the key rising from it.
BASELINE_Y = H - PAD
TOP_Y = PAD
LEFT_X, RIGHT_X = PAD, W - PAD
KEY_W = 160
KEY_H = 190
KEY_LEFT = (W - KEY_W) // 2
KEY_RIGHT = KEY_LEFT + KEY_W
FT_Y = BASELINE_Y - KEY_H
ARC_R = 190


def draw(highlight: str, path: Path) -> None:
    img = Image.new("RGB", (W, H), COURT)
    d = ImageDraw.Draw(img)

    def colour(name: str) -> str:
        return HIGHLIGHT if name == highlight else LINE

    def width(name: str) -> int:
        return 7 if name == highlight else 3

    # Three-point arc: a semicircle centred on the basket.
    cx, cy = W // 2, BASELINE_Y - 40
    d.arc(
        [cx - ARC_R, cy - ARC_R, cx + ARC_R, cy + ARC_R],
        start=180, end=360,
        fill=colour("three-point"), width=width("three-point"),
    )
    # Sidelines
    for x in (LEFT_X, RIGHT_X):
        d.line([(x, TOP_Y), (x, BASELINE_Y)], fill=colour("sideline"), width=width("sideline"))
    # Half-court line (the top edge of this view)
    d.line([(LEFT_X, TOP_Y), (RIGHT_X, TOP_Y)], fill=colour("halfcourt"), width=width("halfcourt"))
    # The key
    d.line([(KEY_LEFT, BASELINE_Y), (KEY_LEFT, FT_Y)], fill=LINE, width=3)
    d.line([(KEY_RIGHT, BASELINE_Y), (KEY_RIGHT, FT_Y)], fill=LINE, width=3)
    # Free-throw line
    d.line([(KEY_LEFT, FT_Y), (KEY_RIGHT, FT_Y)], fill=colour("free-throw"), width=width("free-throw"))
    # Baseline
    d.line([(LEFT_X, BASELINE_Y), (RIGHT_X, BASELINE_Y)], fill=colour("baseline"), width=width("baseline"))
    # The hoop, for orientation.
    d.ellipse([cx - 12, cy - 12, cx + 12, cy + 12], outline=LINE, width=3)

    img.save(path, "PNG", optimize=True)


target = Path("apps/questions/resources/nba/images")
target.mkdir(parents=True, exist_ok=True)
for name in ("free-throw", "three-point", "baseline", "halfcourt"):
    draw(name, target / f"court-{name}-line.png")
    print("wrote", target / f"court-{name}-line.png")
