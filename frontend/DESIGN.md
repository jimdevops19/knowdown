# knowdown design system — FLOODLIT

The values live in `src/index.css`, which is the only file that defines a colour,
a typeface or a radius. This document is the *why*, and the rules that keep the
next change inside the system.

If you are an agent or a person adding UI to this app: read the four rules in
"Non-negotiables" before writing a class name.

---

## The problem this system exists to solve

The previous system was violet primary, cyan accent, blue-black surfaces,
Inter + Space Grotesk, 20px corners, frosted-glass panels, coloured glow
shadows, and a violet→cyan gradient on the hero and the logo.

Every one of those is a documented marker of an interface that no human decided.
The lineage is well traced: Tailwind UI shipped `indigo-500` as a placeholder
accent, that placeholder saturated the training data, and models now emit it as
the statistical average of "a web app". Design commentary in 2026 lists the
tells explicitly — indigo-to-purple gradients, Inter (and the Space Grotesk
pairing), permanent dark mode with mid-grey body text, gradients everywhere,
large coloured glows, pill-rounded everything, a centred hero, and a row of
three identical feature cards with thin-line icons.

Sources this system was built against:

- [AI Slop Fonts and Gradients: The Tells That Give Away AI Design](https://www.925studios.co/blog/ai-slop-design-tells) — 925 Studios
- [AI Design Slop: 16 Patterns That Out Your App as Vibe-Coded](https://www.developersdigest.tech/blog/ai-design-slop-and-how-to-spot-it) — Developers Digest
- [Why Every AI-Built Website Looks the Same (Blame Tailwind's Indigo-500)](https://dev.to/alanwest/why-every-ai-built-website-looks-the-same-blame-tailwinds-indigo-500-3h2p) — DEV
- [Game changers: the designers innovating graphics for sports](https://www.itsnicethat.com/features/forward-thinking-sports-graphic-design-080124) — It's Nice That

The last one supplies the replacement. Sport already has a visual language —
floodlit pitches, scoreboards, broadcast lower-thirds — and it is specific,
old, and nothing like the generated look: flat plates, hard rules, widened
heavy type, one loud colour against ink, and a strictly rationed palette.

---

## The reference

**A live scores app: one hot orange over flat neutral graphite.**

The specific model is LiveScore, whose own stylesheet is essentially three
values — `#ff6b00`, `#fdfdfd` and `#181818` — and almost nothing else. When a
decision is unclear, ask what a scoreboard or a results ticker would do.

---

## Colour

Surfaces are **pure neutral graphite** — no blue cast, and no warm cast either.
An orange this saturated needs a grey ground to stay orange: over a blue-black
it turns into a warning label, and over a warm olive (which an earlier draft of
this system used) it turns brown.

| Token | Value | Means, and *only* means |
|---|---|---|
| `court` | `#ff6b00` orange | Primary. Your side, calls to action, "you are here". |
| `deep-court` | `#e05e00` | `court` hover / pressed. |
| `volt` | `#ff8f2e` | **Live**, as the same orange one step brighter: the clock, the pulse, links, the search rings. |
| `deep-volt` | `#eb7d1a` | `volt` hover / pressed. |
| `gold` | `#ffc94d` | **Rank only** — the podium, level bands, badges. Not match results. |
| `correct` | `#23df8c` | A right answer, and a won match — the same claim at two scales. |
| `wrong` | `#ff2e4d` | A wrong answer, and destructive actions. |
| `rival` | `#2f9bff` azure | The opponent's side of any scoreboard. |
| `idle` | `#8a8a8a` | Waiting, disabled, neither-side. |
| `chalk` | `#fdfdfd` | Text. Near-white — never `text-white` (use the token). |
| `ash` | `#a3a3a3` | Secondary text. |
| `void` `court-black` `panel` `raised` | `#0b0b0b` `#121212` `#181818` `#242424` | Surfaces, deepest to highest. |

**There is one brand colour and it is orange.** Primary and "live" are
deliberately *not* separate hues. An earlier draft split them — lime for the
primary, orange for live — which meant the matchmaking rings pulsed in one
colour while the button that started the match was another. They are the same
idea, so they are the same colour.

Everything else is functional and chosen to sit far from the orange:

- **Orange vs azure** carries the most important distinction in the app — your
  side vs your opponent's, read on a phone at arm's length with seconds on the
  clock. It survives both common forms of colour blindness, and it is the oldest
  pair of kits in sport.
- **`wrong` is pushed hard to crimson**, because the orange-red it would
  naturally sit at is a near-match for the brand.
- **`gold` is kept light rather than bronzed.** Bronze sits on top of the
  orange; rank separates from brand by *lightness*, since it cannot by hue.
- **Winning a match is green, not gold.** Gold started out doing two jobs —
  standing (where it is earned over time) and results (where it is decided in
  four minutes) — and a warm-yellow trophy sitting a few degrees off the brand
  orange made the summary screen read as two oranges. Green already means "you
  got this right"; a won match is that same statement about the whole match, and
  it sets win / draw / loss as green / white / grey, three unmistakable values
  that never collide with the brand. Gold now appears only where a *ranking*
  does.

### Two places the single-orange rule is deliberately broken

Both exist because a permanently-lit brand colour stops being a signal:

- **The countdown bar starts white**, not orange. It is on screen for the whole
  of every question; painted orange it would be the largest always-lit brand
  element in the app, and gold → crimson only reads as *rising* if it rises from
  neutral.
- **The focus ring is white.** An orange ring around an orange button is no
  ring at all, and that button is the control most likely to be focused.

Related: the **draw** status chip is white, not the primary. A draw is the one
result that is not hot, and as orange it was indistinguishable from the LIVE
chip beside it in a match list.

### Contrast

Every foreground/background pair in use has been measured; all clear WCAG AA and
most clear AAA. Three were fixed because they did not:

- **Near-white on `#ff6b00` is 2.81:1 and fails AA.** LiveScore ships exactly
  that pairing; it is the one thing from their stylesheet not to copy. Dark ink
  on the same fill is 6.89:1.
- `idle` was lifted until it cleared 4.5:1 on `panel`.
- The danger button's label was flipped to dark ink (chalk on that red is 3.1:1).

The rule that falls out: **a bright fill takes dark ink.** Every one of `court`,
`volt` and `wrong` is read as `text-void`, never `text-chalk`.

---

## Type

| Role | Face | Why |
|---|---|---|
| Display | **Archivo Variable**, width axis at `112%`, weight 700–800 | Widened, it is scoreboard lettering. The width is the strongest brand signal in the app and it costs one axis, not a second file. Imported from `wdth.css`, not `index.css` — that build is the one carrying the width axis. |
| Body | **IBM Plex Sans** 400–700 | A working face with real quirks, legible at 14px on a phone, and emphatically not the default. |

Inter and Space Grotesk are both out, and not only on grounds of taste: the
pairing is itself listed as a tell.

**Caps are for labels, never for prose.** Buttons, status chips, section
headings and tab labels are upper-cased and tracked. Headings, question text
and body copy are not. The default look blurs this by upper-casing everything
small and grey.

---

## Shape

`--radius-btn: 6px` · `--radius-input: 6px` · `--radius-tile: 8px` ·
`--radius-card: 10px` · `--radius-modal: 14px`

Cut, not pillowed. The previous scale topped out at 24px — the soft-card look
that ships with the default palette. Broadcast graphics are plates with a
barely-broken corner.

**Round is reserved** for things that are physically round: avatars, the live
recording dot, the matchmaking radar ring. Nothing else is a pill.

---

## Emphasis, depth and texture

- **Emphasis is a keyline**, not a halo: `shadow-edge-*` is one crisp pixel of
  the colour with no blur. The blurred coloured glow it replaced is the other
  half of the generated look, and on an OLED phone it turns a clean dark screen
  muddy.
- **Surfaces are opaque.** The `plate` utility is a flat panel plus a hairline,
  with its top edge one shade brighter — a plate catching the floodlight. It
  replaced a `backdrop-filter` glass treatment that made every panel a slightly
  different colour depending on what scrolled behind it, and cost a backdrop
  composite per surface on phones.
- **State is a bar on an edge**, not a wash across a fill. Answer tiles,
  scoreboard sides, sidebar rows and the result banner are all marked this way.
  A tint has to stay faint to keep text legible, so at arm's length it stops
  reading at all; a solid bar of full-strength colour reads across a room.
- **The background is one white floodlight** hung high and centred, with a faint
  orange spill low down — the brand bleeding up from under the content — over
  hairline stripes at ~1.5%. The stripes are invisible as stripes and are the
  point: texture is what a default dark theme never has.

---

## Non-negotiables

1. **No violet, indigo, purple or cyan as a UI colour.** Not as a token, not as
   a one-off Tailwind class, not in an SVG.

   The one exception is deliberate and worth knowing about: player avatars hash
   a name to a hue in a band running green → teal → deep blue (`lib/nameColor`).
   Those are rendered dark and desaturated, so the teal end is a deep slate, not
   an accent. The band excludes the warm quarter on purpose — orange in this app
   means "you can act on this" or "this is happening now", and a player whose
   initials hashed to orange would be wearing an affordance.
2. **No gradients** except the winner's shimmer sweep. No gradient text, no
   corner blooms, no two-stop diagonal fills. Emphasis comes from width, weight
   and flat colour.
3. **No `text-white` / `bg-white` / `border-white`.** Use `chalk`. Not because
   the value differs much — `chalk` *is* near-white — but because a hard-coded
   `white` is a colour that escapes the token layer, and the token layer is the
   only reason this repaint was a one-file change.
4. **Never introduce a raw colour.** If a component needs a colour it does not
   have, the question is which of the nine semantic tokens it means. If the
   honest answer is "none", it probably needs no colour at all.

And two layout habits worth naming, since both were removed from this app and
both are listed tells:

- **No centred hero** over a balanced sentence and a grey paragraph.
- **No row of three identical cards** with a thin-line icon each. A list of
  rules is a list: one plate, hairline-divided, numbered in the margin.
