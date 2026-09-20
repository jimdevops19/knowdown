---
name: mascot-avatars
description: Draw a new knowdown mascot avatar, or change an existing one. Use when asked to add an animal to the avatar set, add a mascot for a team or category, redraw a mark that reads badly, add a new ball livery, or when a mascot key has to be renamed or retired. Covers the drawing rules, the 64-grid skeleton, the ball, and the four files a new mascot touches.
---

# Drawing a knowdown mascot

The set is forty-one flat-vector animal heads on a round plate, drawn as SVG
strings in `frontend/src/components/avatars/`. They are the app's avatars: a
player picks one on `/me` and wears it on the ladder, the box score and the
live scoreboard.

**Read `frontend/src/components/avatars/primitives.ts` before drawing
anything.** It is short, and it is the contract. This file is the *why* and the
checklist around it.

## The one rule everything else serves

**The skeleton never moves.** Every mark is a single call to `mascot()`, and
what a mark may change is `fur`, `ears`, `muzzle`, `extra`, `eyes` and nothing
else. The plate (r 32 at 32,32), the head mass (rx 19 / ry 18 at 32,34) and the
eye positions (25 and 39, around y 31) are identical across all forty-one.

That is what makes forty-one animals read as one team. Two marks whose eyes sit
at different heights do not look like two members of a set, they look like two
illustrators. If a new animal "needs" the eyes moved, it does not — it needs a
different muzzle.

## The grid

64×64, emitted as the body of an `<svg viewBox="0 0 64 64">`. Nothing in the
module renders its own element; `Mascot` supplies it.

| Slot | Drawn | What belongs there |
|---|---|---|
| `ears` | **behind** the head | ears, horns, antlers, crest, mane, hair, a shell |
| `muzzle` | on the head, **under** the eyes | snout, beak base, face mask, cheek patch |
| `eyes` | four presets | `normal`, `wide`, `squint`, `dot` — a *treatment*, never a position |
| `extra` | **over** everything | nose, mouth, brows, markings, gear, and the ball |

Anything that must sit on top of the eyes (a bandit mask, a pale face mask with
dark eyes over it, coloured irises) goes in `extra` and redraws the eyes there.
That is normal — see `raccoon`, `timber-wolf`, `hawk`.

## The ball

The second and third groups each hold one. `holding(tone, kind)` appended to the
**end** of `extra` draws a paw in `tone` — a darker shade of that animal's own
fur — and a ball on top of it.

- Four liveries: `orange`, `aba`, `white`, `lime` (`BALLS` in `primitives.ts`).
- r = 4.6, held at (48, 45.5). Very small on purpose. **Do not enlarge it.**
- Be honest about the floor: at 24px the ball is ~3px across and reads as a dot
  of colour. That is the price of "very, very small", and it is why the livery
  is the picker's filter — the colour is the part that survives.
- The founding sixteen hold nothing, and that is deliberate. If every mascot
  held a ball the ball would stop meaning anything. Leave them empty-handed.

## Drawing rules that were learned the hard way

Each of these cost a redraw. They are not style preferences.

1. **A new mark must not look like an existing one.** Check the neighbours
   first: there is already a Wolf *and* a Timber wolf, a Bear *and* a Grizzly, a
   Falcon *and* a Hawk. Each pair is separated by something structural — fur
   value, a face mask, eye colour, a jaw — not by a hue nudge.
2. **Horns are not ears.** A tapered upright shape beside a head reads as an
   ear whatever you fill it with. A horn leaves the temple *sideways* and turns
   up; a stroked arc (`stroke-linecap="round"`, width ~5) says it in one line.
   See `bull`, and `ram` before it.
3. **A beak is one path, not two.** A hook drawn as a second shape leaves a gap
   that reads as a drip of paint. See `hawk`.
4. **A dark mass across the mouth reads as a muzzle strap**, not as an animal's
   jaw. Stripes, teeth or a snout shape instead. See `hornet`.
5. **Fine seams and hairlines vanish below 40px.** Nothing thinner than ~1.6
   stroke units, and nothing that must be *counted* to be understood.
6. **Gear is the exception, not the look.** A headband, a whistle, a cap: one
   founding mark in four has a prop and the rest are just the animal.

## Where a mascot lives — all four files

A mascot is not done until all four agree. There is a test on each side that
fails if they do not.

1. `frontend/src/components/avatars/marks.ts` — the drawing, with its **key**,
   label and ball. Append to the group it belongs to.
2. `backend/apps/players/constants.py` — add the key to `MASCOT_KEYS`. This is
   the allow-list that makes a bogus key a 400 rather than a blank disc.
3. `backend/apps/players/tests/test_api.py` — the count in
   `test_every_key_the_allow_list_names_is_accepted` (`assertEqual(len(...), 41)`).
4. Nothing else. The picker, the profile, the ladder and the live scoreboard all
   read `MARKS`, so a new mark appears everywhere on its own.

The mirror between (1) and (2) is guarded by
`MascotTests.test_the_allow_list_is_the_set_the_client_can_draw`, which reads
`marks.ts` as text from the Python side. If you rename a field in `marks.ts`,
check that test still matches the file's shape (`key: 'raptor',`).

## The key is permanent

`key` is what is stored on the player row. **Append-only.**

- Re-spelling a key silently un-picks every player who chose it.
- Retiring a mark leaves its key stored on rows that chose it; the client falls
  back to initials for a key it cannot draw, so removing one is survivable but
  it is still a choice somebody made being taken away. Prefer redrawing.
- Two marks may not share a label either. When a name collided, the *older*
  mark was renamed and kept its key — `ox` is labelled "Ox" and `falcon` is
  labelled "Falcon" for exactly this reason. Labels are free to change; keys
  are not.

## Checking the work

Do not ship a mark you have not looked at. Render the set to a file and
screenshot it — at 150px to judge the drawing, and at 40px and 24px because
those are the sizes it actually ships at (the ladder row and the scoreboard
chip). A mark that only works at 150px does not work.

```sh
cd frontend
cat > .render.ts <<'EOF'
import { MARKS } from './src/components/avatars/marks'
const at = (n: number) =>
  MARKS.map((m) => `<svg viewBox="0 0 64 64" width="${n}" height="${n}" style="border-radius:50%">${m.svg}</svg>`).join('')
console.log(`<!doctype html><meta charset="utf-8"><body style="background:#0a2637">
<div>${at(150)}</div><div>${at(40)}</div><div>${at(24)}</div>`)
EOF
npx tsx .render.ts > /tmp/marks.html && rm .render.ts
```

Then open `/tmp/marks.html`, or screenshot it headless:

```sh
"$HOME/Library/Caches/ms-playwright/chromium-1243/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing" \
  --headless --disable-gpu --hide-scrollbars --force-device-scale-factor=2 \
  --window-size=1200,900 --screenshot=/tmp/marks.png file:///tmp/marks.html
```

Finally, from `frontend`: `npx tsc --noEmit -p tsconfig.app.json` and
`npm test`; from `backend`: `uv run python manage.py test apps.players`.

## Adding a fifth livery

Add it to `BALLS` in `primitives.ts` and it appears in the picker's filter row
on its own. Two things to hold to: the seam colour must survive against the
*pale* animals as well as the dark ones (this is why the white ball's seams are
slate rather than ink), and a livery with fewer than three or four marks reads
as a mistake rather than as a group — add the animals with it, not after it.
