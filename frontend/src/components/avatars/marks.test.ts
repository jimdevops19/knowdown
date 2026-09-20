import { describe, expect, it } from 'vitest'
import { MARKS, getMark } from './marks'

/*
 * The marks are drawings, and a test cannot look at a drawing. What it *can*
 * hold is everything around them that would break quietly:
 *
 *  · the keys, which are stored on player rows and are therefore permanent;
 *  · the fact that each mark went through `mascot()` rather than being pasted
 *    in as loose markup;
 *  · the fallback, which is what an older client does with a newer row.
 */
describe('the mascot set', () => {
  it('has no two marks answering to the same key', () => {
    const keys = MARKS.map((mark) => mark.key)
    expect(new Set(keys).size).toBe(keys.length)
  })

  it('spells every key the way a URL would', () => {
    for (const mark of MARKS) expect(mark.key).toMatch(/^[a-z][a-z-]*[a-z]$/)
  })

  it('draws every mark on the shared skeleton', () => {
    // Not an assertion about how a mascot *looks* — an assertion that it went
    // through `mascot()` rather than being pasted in as loose markup, which is
    // what keeps the plate and the head mass identical across the set.
    for (const mark of MARKS) {
      expect(mark.svg).toContain('<circle cx="32" cy="32" r="32"')
      expect(mark.svg).toContain('<ellipse cx="32" cy="34" rx="19" ry="18"')
    }
  })

  it('gives every mark that holds a ball exactly one', () => {
    for (const mark of MARKS) {
      const balls = mark.svg.match(/<circle cx="48" cy="45\.5" r="4\.6"/g) ?? []
      expect(balls.length).toBe(mark.ball === null ? 0 : 1)
    }
  })

  it('falls back rather than rendering a hole for a key it does not know', () => {
    expect(getMark('tyrannosaurus')).toBeNull()
    expect(getMark(null)).toBeNull()
    expect(getMark('')).toBeNull()
  })
})
