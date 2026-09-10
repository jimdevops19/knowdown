import { useEffect, useState } from 'react'

/*
 * A value that lags behind the one given, settling only once it has stopped
 * changing for `delay`. Used to keep a keystroke from being a request: the
 * display-name field checks availability as you type, and without this it would
 * ask the server once per character.
 */
export function useDebouncedValue<T>(value: T, delay = 350): T {
  const [settled, setSettled] = useState(value)

  useEffect(() => {
    const timer = setTimeout(() => setSettled(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])

  return settled
}
