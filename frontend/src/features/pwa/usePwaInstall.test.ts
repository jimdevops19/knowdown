import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import { usePwaInstall } from './usePwaInstall'

/*
 * The branching in this hook is all platform sniffing, and the cost of getting
 * it wrong is asymmetric: an iOS tip shown on Android describes a Share sheet
 * that isn't there, and a missed dismissal nags somebody on every page load.
 * So these tests drive the three inputs the hook actually reads — the
 * Chromium event, the user agent, and localStorage.
 */

/** jsdom has no matchMedia; the hook asks it whether we are already installed. */
function stubDisplayMode(standalone: boolean) {
  vi.stubGlobal(
    'matchMedia',
    vi.fn(() => ({ matches: standalone })),
  )
}

function stubUserAgent(ua: string) {
  Object.defineProperty(window.navigator, 'userAgent', { value: ua, configurable: true })
}

const IPHONE_SAFARI =
  'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1'
const ANDROID_CHROME =
  'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36'

/** The one-shot event Chromium hands over instead of showing its own infobar. */
function beforeInstallPrompt() {
  const event = new Event('beforeinstallprompt') as Event & {
    prompt: () => Promise<void>
    userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>
  }
  event.prompt = vi.fn(async () => {})
  event.userChoice = Promise.resolve({ outcome: 'accepted' as const })
  return event
}

afterEach(() => {
  localStorage.clear()
  vi.unstubAllGlobals()
  stubUserAgent(ANDROID_CHROME)
})

describe('usePwaInstall', () => {
  it('offers nothing until the browser says the app is installable', () => {
    stubDisplayMode(false)
    stubUserAgent(ANDROID_CHROME)
    const { result } = renderHook(() => usePwaInstall())
    expect(result.current.kind).toBe('unavailable')
  })

  it('offers a one-tap install once Chromium fires beforeinstallprompt', async () => {
    stubDisplayMode(false)
    stubUserAgent(ANDROID_CHROME)
    const { result } = renderHook(() => usePwaInstall())

    const event = beforeInstallPrompt()
    act(() => {
      window.dispatchEvent(event)
    })
    expect(result.current.kind).toBe('prompt')

    // The event is spent by prompting: after one round trip the hook must not
    // offer a second install off the same (now dead) event.
    await act(async () => {
      if (result.current.kind === 'prompt') await result.current.install()
    })
    expect(event.prompt).toHaveBeenCalledOnce()
    expect(result.current.kind).toBe('unavailable')
  })

  it('falls back to Share-sheet instructions on iOS Safari, which has no event', () => {
    stubDisplayMode(false)
    stubUserAgent(IPHONE_SAFARI)
    const { result } = renderHook(() => usePwaInstall())
    expect(result.current.kind).toBe('ios')
  })

  it('stays quiet in an in-app browser, whose share sheet cannot install', () => {
    stubDisplayMode(false)
    stubUserAgent(`${IPHONE_SAFARI} Instagram 300.0.0.0`)
    const { result } = renderHook(() => usePwaInstall())
    expect(result.current.kind).toBe('unavailable')
  })

  it('stays quiet once the app is running standalone', () => {
    stubDisplayMode(true)
    stubUserAgent(IPHONE_SAFARI)
    const { result } = renderHook(() => usePwaInstall())
    expect(result.current.kind).toBe('unavailable')
  })

  it('remembers a dismissal across visits', () => {
    stubDisplayMode(false)
    stubUserAgent(IPHONE_SAFARI)
    const first = renderHook(() => usePwaInstall())
    if (first.result.current.kind !== 'ios') throw new Error('expected the iOS tip')
    const { dismiss } = first.result.current
    act(() => dismiss())
    expect(first.result.current.kind).toBe('unavailable')

    // A fresh mount is the next page load: the banner must not come back.
    const second = renderHook(() => usePwaInstall())
    expect(second.result.current.kind).toBe('unavailable')
  })

  it('drops the banner when the app is installed from the browser menu', () => {
    stubDisplayMode(false)
    stubUserAgent(ANDROID_CHROME)
    const { result } = renderHook(() => usePwaInstall())
    act(() => {
      window.dispatchEvent(beforeInstallPrompt())
    })
    expect(result.current.kind).toBe('prompt')

    act(() => {
      window.dispatchEvent(new Event('appinstalled'))
    })
    expect(result.current.kind).toBe('unavailable')
  })
})
