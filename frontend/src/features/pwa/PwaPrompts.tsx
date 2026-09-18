import { useEffect, useRef, useState } from 'react'
import { useRegisterSW } from 'virtual:pwa-register/react'
import { RefreshCw, Share, SquarePlus } from 'lucide-react'
import { Button } from '../../components/Button'
import { LogoMark } from '../../components/Logo'
import { PromptBanner } from '../../components/PromptBanner'
import { usePwaInstall } from './usePwaInstall'

/*
 * The two pieces of UI a PWA needs and nothing else does:
 *
 *  1. **Update ready** — the service worker has a newer build downloaded and
 *     waiting. We ask rather than swap (registerType: 'prompt' in
 *     vite.config.ts): reloading somebody six seconds into a question to ship
 *     a CSS tweak is the kind of "helpful" that loses them the match.
 *  2. **Install** — the home-screen invitation (see usePwaInstall).
 *
 * Both wear PromptBanner, which owns where a standing prompt sits and how it
 * folds on a phone.
 *
 * Mounted once, in AppProviders, so it survives every route change.
 */

/** How often an open tab re-checks for a new build (an hour). */
const UPDATE_CHECK_MS = 60 * 60 * 1000

/** How long a first-time visitor gets to look around before being asked. */
const INSTALL_DELAY_MS = 45_000

/** How often the app re-checks whether the moment is right, once it wasn't. */
const RECHECK_MS = 10_000

/* Screens where no banner may appear: a question is open, a clock is running,
 * and the answer tiles reach the full height of a phone. This is the same rule
 * <Toast /> holds itself to — nothing slides in over a live board — and it
 * applies to the update prompt as much as the install one, since neither is
 * news the player asked for mid-match.
 *
 * The check reads `window.location` rather than `useLocation` because this
 * component is mounted *outside* the router (AppProviders wraps
 * RouterProvider), which is also why it is polled rather than subscribed to. */
function inMatch(): boolean {
  const path = window.location.pathname
  return path.startsWith('/match/') || /^\/play\/.+/.test(path)
}

/**
 * True once `delayMs` has passed *and* the player is not mid-match.
 *
 * One-way: once a prompt has been allowed through it stays up until it is
 * answered or dismissed, rather than vanishing the moment the next match
 * starts — a banner that disappears while being read is worse than one that
 * waited a little longer to arrive.
 */
function useQuietMoment(delayMs: number): boolean {
  const [quiet, setQuiet] = useState(delayMs === 0 && !inMatch())
  useEffect(() => {
    if (quiet) return
    let poll: ReturnType<typeof setInterval> | undefined
    const tick = () => {
      if (!inMatch()) setQuiet(true)
    }
    const delay = setTimeout(() => {
      tick()
      poll = setInterval(tick, RECHECK_MS)
    }, delayMs)
    return () => {
      clearTimeout(delay)
      clearInterval(poll)
    }
  }, [quiet, delayMs])
  return quiet
}

function UpdateBanner({ onDismiss, onReload }: { onDismiss: () => void; onReload: () => void }) {
  return (
    <PromptBanner
      media={<RefreshCw size={18} className="shrink-0 text-volt" />}
      onDismiss={onDismiss}
      dismissLabel="Dismiss update"
      actions={
        <Button size="sm" onClick={onReload}>
          Reload
        </Button>
      }
    >
      <p className="text-sm font-semibold text-chalk">A new version of knowdown is ready</p>
      <p className="text-[13px] text-ash">Reload between matches.</p>
    </PromptBanner>
  )
}

function InstallBanner() {
  const install = usePwaInstall()
  // Don't ambush a first-time visitor: let them look around for a minute, and
  // then wait for a screen that isn't a live match.
  const ripe = useQuietMoment(INSTALL_DELAY_MS)

  if (!ripe || install.kind === 'unavailable') return null

  if (install.kind === 'ios') {
    return (
      <PromptBanner
        // The mark itself rather than a download glyph: it is what the banner
        // is offering, and it is the thing they will be looking for on the
        // home screen afterwards.
        media={<LogoMark size={28} />}
        onDismiss={install.dismiss}
        dismissLabel="Dismiss install tip"
      >
        <p className="text-sm font-semibold text-chalk">Add knowdown to your Home Screen</p>
        <p className="flex flex-wrap items-center gap-1 text-[13px] text-ash">
          Tap <Share size={13} className="inline text-volt" /> Share, then
          <SquarePlus size={13} className="inline text-volt" /> Add to Home Screen.
        </p>
      </PromptBanner>
    )
  }

  return (
    <PromptBanner
      media={<LogoMark size={28} />}
      onDismiss={install.dismiss}
      dismissLabel="Not now"
      actions={
        <Button size="sm" onClick={() => void install.install()}>
          Install
        </Button>
      }
    >
      <p className="text-sm font-semibold text-chalk">Install knowdown</p>
      <p className="text-[13px] text-ash">Full screen, own icon, opens instantly.</p>
    </PromptBanner>
  )
}

export function PwaPrompts() {
  // The registration lives here rather than inside UpdateBanner so the two can
  // be ordered against each other: an update always outranks an invitation to
  // install, so the install prompt stands down while a build is waiting.
  // (PromptBanner's stack would happily show both — we just don't want it to.)

  // The poll's handle, kept so it can be stopped. `onRegisteredSW` is a
  // callback the registration calls, not an effect, so there is no cleanup to
  // return from it — without the ref the timer would outlive this component.
  const poll = useRef<ReturnType<typeof setInterval> | undefined>(undefined)
  useEffect(() => () => clearInterval(poll.current), [])

  const {
    needRefresh: [needRefresh, setNeedRefresh],
    updateServiceWorker,
  } = useRegisterSW({
    onRegisteredSW(_url, registration) {
      // A phone left on the rankings for a day would otherwise never notice a
      // deploy: the worker only checks on navigation. Poll, but gently, and
      // skip it while offline so it isn't a wasted wake-up.
      if (!registration) return
      // Re-registering replaces the timer rather than adding a second one.
      clearInterval(poll.current)
      poll.current = setInterval(() => {
        if (navigator.onLine) void registration.update()
      }, UPDATE_CHECK_MS)
    },
  })

  // An update is ready the moment the worker says so, but it still waits for
  // the player to be off the board.
  const quiet = useQuietMoment(0)

  if (!quiet) return null

  return needRefresh ? (
    <UpdateBanner
      onDismiss={() => setNeedRefresh(false)}
      // `true` reloads the page once the waiting worker takes over.
      onReload={() => void updateServiceWorker(true)}
    />
  ) : (
    <InstallBanner />
  )
}
