/*
 * The mascot set. See `marks.ts` for the marks themselves and
 * `.claude/skills/mascot-avatars/` for how to draw another one.
 */
export { Mascot } from './Mascot'
export { MARKS, getMark, type Mark } from './marks'
export { BALLS, ball, type BallKind } from './primitives'

import { MARKS } from './marks'

/** Every valid key. Mirrored by `MASCOT_KEYS` in `apps/players/constants.py`,
 *  which is the copy that decides whether a PATCH is a 200 or a 400. */
export const MASCOT_KEYS: string[] = MARKS.map((mark) => mark.key)
