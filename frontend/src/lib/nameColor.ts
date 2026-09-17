/*
 * A stable hue per identity, so a player reads as the same colour everywhere
 * they appear — the ladder, a box score, the avatar beside their name.
 *
 * Derived from the string rather than stored, which matters more here than it
 * would elsewhere: during a live match the client knows its opponent only by a
 * UUID (the socket never sends a name — see `features/play/MatchPage`), and
 * this is what lets that opponent still be a consistent *someone* on screen
 * rather than a grey blank.
 *
 * FNV-1a rather than a hand-rolled sum: a plain character sum gives anagrams
 * the same colour, and two players called "jim" and "mij" being visually
 * identical is exactly the collision that matters in a two-person game.
 */
export function hashHue(value: string): number {
  let hash = 0x811c9dc5
  for (let i = 0; i < value.length; i++) {
    hash ^= value.charCodeAt(i)
    // The FNV prime, by shift-and-add: `hash * 16777619` overflows a JS number
    // into imprecision, while `Math.imul` and this form stay in 32-bit land.
    hash = (hash + ((hash << 1) + (hash << 4) + (hash << 7) + (hash << 8) + (hash << 24))) >>> 0
  }
  return HUE_BAND_START + (hash % HUE_BAND_WIDTH)
}

/*
 * The hue is confined to one arc of the wheel: roughly 140°–265°, green through
 * teal to deep blue.
 *
 * Two constraints put it there. Unconstrained, this returned any of 360 hues,
 * which made the avatars the one place in the app still issuing violets and
 * magentas — and a dozen of them down a ladder undoes a deliberate palette on
 * its own, because the eye reads a page's colour from the repeated elements
 * rather than from the one accent.
 *
 * The band then deliberately *excludes* the warm quarter the brand lives in.
 * An avatar is decoration attached to a name; the orange in this app means "you
 * can act on this" or "this is happening now", and a player whose initials
 * happen to hash to orange would be wearing an affordance. Cool identity tints
 * against a warm UI keeps the two vocabularies apart — and it is the same
 * separation the scoreboard already makes between your side and theirs.
 *
 * These are rendered dark and well desaturated (see `Avatar`), so the teal end
 * of the band is a deep slate rather than anything like a bright cyan accent.
 *
 * 125° is still far more separation than the ~12 identities visible on any one
 * screen need — two players are distinguishable long before their hues are.
 */
const HUE_BAND_START = 140
const HUE_BAND_WIDTH = 125
