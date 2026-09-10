import { Button } from '../components/Button'
import { LogoMark } from '../components/Logo'

/*
 * 500 — something threw on its way to the screen.
 *
 * "Try again" is a hard reload rather than a re-render, deliberately: whatever
 * state produced the crash is in memory, and re-rendering it would only crash
 * again.
 */
export function ServerErrorPage() {
  return (
    <div className="flex flex-col items-center gap-5 py-16 text-center">
      <LogoMark size={56} className="opacity-60" />
      <div>
        <h1 className="font-display text-3xl font-bold text-chalk">That broke</h1>
        <p className="mt-2 max-w-sm text-ash">
          Something went wrong on our side. Reloading usually clears it.
        </p>
      </div>
      <Button onClick={() => window.location.reload()}>Reload</Button>
    </div>
  )
}
