import { getMark } from './marks'

/*
 * One mascot, drawn.
 *
 * `dangerouslySetInnerHTML` is the right call and not a shortcut: every string
 * it renders is authored in `marks.ts` and built by `mascot()`, none of it is
 * ever a value that came off the network. What *does* come off the network is
 * the `mascotKey`, and that only ever selects a mark or misses — an unknown key
 * returns `null` here and the caller falls back to initials.
 *
 * Rendering these as React elements instead would mean parsing the same markup
 * into ~40 components' worth of JSX for no gain: the marks are static, they
 * have no state, and this way the whole set costs one string per avatar.
 */
export function Mascot({
  mascotKey,
  size = 40,
  className,
}: {
  mascotKey: string
  size?: number
  className?: string
}) {
  const mark = getMark(mascotKey)
  if (!mark) return null

  return (
    <svg
      viewBox="0 0 64 64"
      width={size}
      height={size}
      role="img"
      aria-label={mark.label}
      className={className}
      dangerouslySetInnerHTML={{ __html: mark.svg }}
    />
  )
}
