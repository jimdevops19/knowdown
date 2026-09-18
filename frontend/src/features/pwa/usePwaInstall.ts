import { useCallback, useEffect, useState } from 'react'

/*
 * "Add knowdown to your home screen" — the one thing that turns this from a
 * site into the game it is meant to be on a phone: installed, it runs
 * standalone (no URL bar, no tab strip, its own icon and splash screen), which
 * on the question board is the difference between a full-height set of answer
 * tiles and a set squeezed under browser chrome.
 *
 * Two very different platforms hide behind one hook:
 *
 *  - Chromium (Android, desktop) fires `beforeinstallprompt` once it decides
 *    the app is installable. `preventDefault()` suppresses the browser's own
 *    mini-infobar and hands us the event to fire later, from a real user
 *    gesture. The event is one-shot: after `prompt()` it cannot be reused.
 *  - iOS Safari has no such event at all. Installing is a manual trip through
 *    the Share sheet, so all we can do is *say so* — and only on iOS, only in
 *    Safari, and only when we are not already installed.
 *
 * A dismissal sticks (localStorage): being asked to install on every page load
 * is exactly the phone experience this is trying to buy its way out of.
 */

const DISMISSED_KEY = 'knowdown:install-dismissed'

/** Social apps whose in-app browser can't install anything (see isIosSafari). */
const IN_APP_BROWSER =
  /instagram|FBAN\/|FBAV\/|FB_IAB|bytedancewebview|musical_ly|TTWebView|twitter|snapchat|LinkedInApp/i

/** Chromium-only event; not in lib.dom, so it is typed here. */
interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>
}

/** True when the page is running as an installed app rather than in a tab. */
export function isStandalone(): boolean {
  return (
    window.matchMedia('(display-mode: standalone)').matches ||
    // iOS's pre-standard flag, still the only signal Safari gives.
    ('standalone' in window.navigator && window.navigator.standalone === true)
  )
}

function isIosSafari(): boolean {
  const ua = window.navigator.userAgent
  // iPadOS 13+ reports as a Mac, so touch points are what separate an iPad from
  // a desktop. Chrome/Firefox/Edge on iOS are Safari underneath but cannot
  // install, so they are excluded by their own UA tokens.
  const ios =
    /iphone|ipod|ipad/i.test(ua) ||
    (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1)
  // A social app's in-app browser is a WKWebView and looks like Safari here,
  // but its share sheet has no "Add to Home Screen" — the instructions would
  // describe a button that isn't there. (Chromium's event doesn't fire inside a
  // WebView at all, so only this branch needs the guard.)
  return ios && !/crios|fxios|edgios/i.test(ua) && !IN_APP_BROWSER.test(ua)
}

export type InstallState =
  /** Nothing to offer: already installed, dismissed, or an unsupported browser. */
  | { kind: 'unavailable' }
  /** Chromium: we hold a live prompt event and can install in one tap. */
  | { kind: 'prompt'; install: () => Promise<void>; dismiss: () => void }
  /** iOS: no API — show the Share-sheet instructions instead. */
  | { kind: 'ios'; dismiss: () => void }

export function usePwaInstall(): InstallState {
  const [deferred, setDeferred] = useState<BeforeInstallPromptEvent | null>(null)
  const [dismissed, setDismissed] = useState(
    () => localStorage.getItem(DISMISSED_KEY) === 'true' || isStandalone(),
  )

  useEffect(() => {
    const onBeforeInstall = (event: Event) => {
      event.preventDefault()
      setDeferred(event as BeforeInstallPromptEvent)
    }
    // Installing from the browser's own menu fires this instead — drop the
    // banner rather than inviting somebody to install what they just installed.
    const onInstalled = () => {
      setDeferred(null)
      setDismissed(true)
    }
    window.addEventListener('beforeinstallprompt', onBeforeInstall)
    window.addEventListener('appinstalled', onInstalled)
    return () => {
      window.removeEventListener('beforeinstallprompt', onBeforeInstall)
      window.removeEventListener('appinstalled', onInstalled)
    }
  }, [])

  const dismiss = useCallback(() => {
    localStorage.setItem(DISMISSED_KEY, 'true')
    setDismissed(true)
  }, [])

  const install = useCallback(async () => {
    if (!deferred) return
    await deferred.prompt()
    await deferred.userChoice
    // Spent either way: accepted, or declined and not offered again this visit.
    setDeferred(null)
  }, [deferred])

  if (dismissed) return { kind: 'unavailable' }
  if (deferred) return { kind: 'prompt', install, dismiss }
  if (isIosSafari()) return { kind: 'ios', dismiss }
  return { kind: 'unavailable' }
}
