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
  return hash % 360
}
