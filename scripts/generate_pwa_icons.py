"""Draw every PWA / favicon asset in frontend/public from the app's own mark.

The mark is the ball from frontend/src/components/Logo.tsx — one disc cut on
the diagonal, brand orange against the logo's azure — and it is a circle and a
half-plane rather than artwork, so it is *redrawn* here instead of being traced
from a file. That keeps one source of truth: the geometry and the three colours
below are the same numbers the inline SVG uses, on the same 64-unit grid.

The ball sits on a `void` tile rather than running to the edge. On screen the
mark is a bare disc, because it always has the app's own dark behind it; a
launcher does not offer that, and a disc dropped on whatever ground the OS
picks loses the dark keyline that holds its edge.

Three variants ship, because a launcher does not ask which one it wants:

  icon-*.png           the rounded tile. Android's "any" purpose, and what a
                       desktop install shows.
  icon-maskable-*.png  full bleed, ball shrunk into the 80% safe zone, so
                       Android can crop the tile to a circle/squircle/whatever
                       the launcher uses without slicing the mark.
  apple-touch-icon     180px, square and opaque — iOS rounds it itself, and a
                       transparent corner there comes out black.

Run:  uv run python scripts/generate_pwa_icons.py
"""

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "frontend" / "public"

# index.css --color-court, --color-kit-azure and --color-void: the two kits and
# the ink between them, exactly as on screen.
COURT = "#ff7a14"
AZURE = "#00bdf5"
VOID = "#04202e"

# The 64-unit grid of the source SVG. Everything below is a fraction of the
# icon's side, so one set of numbers covers 16px and 512px alike.
GRID = 64.0
RADIUS = 10 / GRID  # the tile's corner

# The ball, in grid units. Smaller than the on-screen disc (29.25) because here
# it has a tile around it: at 26 the ground reads as a margin rather than as a
# ring of dark squeezed into the corners.
BALL_R = 26.0
SEAM_W = 2.0  # the dark line where the two kits meet

# Draw big, then shrink: PIL has no antialiasing of its own, so the smooth
# edges come from the downsample. 8x is enough that a 16px favicon's disc still
# has a clean curve.
SS = 8


def mark(side: int, *, tile: bool, inset: float = 0.0) -> Image.Image:
    """One icon: void ground, split ball.

    `tile` rounds the corners (the in-app look); a maskable or Apple icon wants
    the ground to run to the edge instead. `inset` shrinks the *ball* towards
    the centre without moving the ground, which is how the maskable variant
    keeps itself inside the safe zone.
    """
    px = side * SS
    img = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    if tile:
        d.rounded_rectangle((0, 0, px - 1, px - 1), radius=RADIUS * px, fill=VOID)
    else:
        d.rectangle((0, 0, px - 1, px - 1), fill=VOID)

    # Grid units → pixels, about the centre, so `inset` shrinks the ball
    # towards the middle without moving the ground under it.
    scale = 1.0 - inset
    c = px / 2
    r = BALL_R / GRID * px * scale

    # The two halves are painted on their own layer and then cut to the disc by
    # a mask, rather than drawn as two arcs. A pieslice pair would butt along
    # the diagonal and leave the shared edge to the rasteriser, which shows as
    # a pale hairline down the seam once the supersample is resampled away.
    kits = Image.new("RGBA", (px, px), AZURE)
    k = ImageDraw.Draw(kits)
    # Everything above the anti-diagonal through the centre: the orange half.
    k.polygon([(c - px, c + px), (c + px, c - px), (c - px, c - px)], fill=COURT)
    k.line(
        [(c - px, c + px), (c + px, c - px)],
        fill=VOID,
        width=max(1, round(SEAM_W / GRID * px * scale)),
    )

    disc = Image.new("L", (px, px), 0)
    ImageDraw.Draw(disc).ellipse((c - r, c - r, c + r, c + r), fill=255)
    img.paste(kits, mask=disc)

    return img.resize((side, side), Image.LANCZOS)


def write(img: Image.Image, name: str, *, opaque: bool = False) -> None:
    if opaque:
        # Flatten onto the app's own dark rather than onto white: iOS
        # composites a transparent touch icon over black, and the rounded
        # corners of the tile would come back as darker notches.
        ground = Image.new("RGB", img.size, VOID)
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

    # Maskable: Android crops up to the outer 20%, so the ball lives inside the
    # middle 80% and the void takes whatever the launcher trims.
    write(mark(192, tile=False, inset=0.2), "icon-maskable-192.png")
    write(mark(512, tile=False, inset=0.2), "icon-maskable-512.png")

    # iOS home screen.
    write(mark(180, tile=False), "apple-touch-icon.png", opaque=True)


if __name__ == "__main__":
    main()
