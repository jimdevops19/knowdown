"""Draw every PWA / favicon asset in frontend/public from the app's own mark.

The mark is the K from frontend/src/components/Logo.tsx — a wide, flat-sided
letter cut out of the orange tile — and it is four path commands rather than
artwork, so it is *redrawn* here instead of being traced from a file. That
keeps one source of truth: the geometry and the two colours below are the same
numbers the inline SVG uses, on the same 32-unit grid.

Three variants ship, because a launcher does not ask which one it wants:

  icon-*.png           the rounded tile, as the app draws it. Android's "any"
                       purpose, and what a desktop install shows.
  icon-maskable-*.png  full bleed, mark shrunk into the 80% safe zone, so
                       Android can crop the tile to a circle/squircle/whatever
                       the launcher uses without slicing the letter.
  apple-touch-icon     180px, square and opaque — iOS rounds it itself, and a
                       transparent corner there comes out black.

Run:  uv run python scripts/generate_pwa_icons.py
"""

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "frontend" / "public"

# index.css --color-court and --color-void. The tile is the brand orange and
# the mark is the app's deepest ink, exactly as on screen.
COURT = "#ff6b00"
VOID = "#0b0b0b"

# The 32-unit grid of the source SVG. Everything below is a fraction of the
# icon's side, so one set of numbers covers 16px and 512px alike.
GRID = 32.0
RADIUS = 5 / GRID  # the tile's corner

# The K, as the two filled paths the SVG draws, in grid units.
#
#   the stem   a plain upright bar down the left
#   the arms   one polygon for both, traced from the SVG's `M24.4 7 …Z`
#
# The arms' inner edge (x=12.2) lands *inside* the stem (which runs to 12.4)
# rather than against it. Butting two fills at the same coordinate leaves a
# hairline of orange between them once PIL's supersample is resampled down, and
# the 512px launcher icon is exactly where that shows.
STEM = (8.0, 7.0, 12.4, 25.0)  # left, top, right, bottom
ARMS = (
    (24.4, 7.0),
    (16.0, 15.2),
    (24.8, 25.0),
    (19.2, 25.0),
    (12.2, 16.9),
    (12.2, 15.2),
    (19.0, 7.0),
)

# Draw big, then shrink: PIL has no antialiasing of its own, so the smooth
# edges come from the downsample. 8x is enough that a 16px favicon's diagonals
# still have clean sides.
SS = 8


def mark(side: int, *, tile: bool, inset: float = 0.0) -> Image.Image:
    """One icon: orange ground, K.

    `tile` rounds the corners (the in-app look); a maskable or Apple icon wants
    the ground to run to the edge instead. `inset` shrinks the *mark* towards
    the centre without moving the ground, which is how the maskable variant
    keeps itself inside the safe zone.
    """
    px = side * SS
    img = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    if tile:
        d.rounded_rectangle((0, 0, px - 1, px - 1), radius=RADIUS * px, fill=COURT)
    else:
        d.rectangle((0, 0, px - 1, px - 1), fill=COURT)

    # Grid units → pixels, about the centre, so `inset` shrinks the letter
    # towards the middle without moving the ground under it.
    scale = 1.0 - inset
    c = px / 2

    def at(x: float, y: float) -> tuple[float, float]:
        return (c + (x - GRID / 2) / GRID * px * scale, c + (y - GRID / 2) / GRID * px * scale)

    left, top, right, bottom = STEM
    d.polygon([at(left, top), at(right, top), at(right, bottom), at(left, bottom)], fill=VOID)
    d.polygon([at(x, y) for x, y in ARMS], fill=VOID)

    return img.resize((side, side), Image.LANCZOS)


def write(img: Image.Image, name: str, *, opaque: bool = False) -> None:
    if opaque:
        # Flatten onto the brand orange rather than onto white: iOS composites
        # a transparent touch icon over black, and the rounded corners of the
        # tile would come back as dark notches.
        ground = Image.new("RGB", img.size, COURT)
        ground.paste(img, mask=img.getchannel("A"))
        img = ground
    path = PUBLIC / name
    img.save(path, "PNG", optimize=True)
    print(f"{path.relative_to(ROOT)}  {img.size[0]}x{img.size[1]}")


def main() -> None:
    PUBLIC.mkdir(parents=True, exist_ok=True)

    # Tab and bookmark strips. Two sizes because browsers pick per surface.
    write(mark(32, tile=True), "favicon-32.png")
    write(mark(16, tile=True), "favicon-16.png")

    # The manifest's "any" icons.
    write(mark(192, tile=True), "icon-192.png")
    write(mark(512, tile=True), "icon-512.png")

    # Maskable: Android crops up to the outer 20%, so the mark lives inside the
    # middle 80% and the orange takes whatever the launcher trims.
    write(mark(192, tile=False, inset=0.2), "icon-maskable-192.png")
    write(mark(512, tile=False, inset=0.2), "icon-maskable-512.png")

    # iOS home screen.
    write(mark(180, tile=False), "apple-touch-icon.png", opaque=True)


if __name__ == "__main__":
    main()
