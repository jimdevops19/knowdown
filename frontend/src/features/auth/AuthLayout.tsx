import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Logo } from '../../components/Logo'

/*
 * The frame around every doorway screen — sign in, sign up, choose a name,
 * reset a password.
 *
 * Standalone rather than inside AppShell, and that is not only cosmetic: the
 * shell's nav is a list of places a signed-out visitor mostly cannot go, and
 * showing it beside a sign-in form invites taps that bounce straight back here.
 * One column, centred, with the brand at the top and nothing else to do.
 *
 * `min-h-dvh` rather than `min-h-screen`: on a phone `vh` doesn't account for
 * the URL bar, so the card would sit a few dozen pixels below centre and the
 * submit button would land under the browser chrome exactly when the keyboard
 * is up.
 */
export function AuthLayout({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string
  subtitle?: ReactNode
  children: ReactNode
  footer?: ReactNode
}) {
  return (
    <div className="px-safe flex min-h-dvh flex-col items-center justify-center py-10">
      <div className="flex w-full max-w-sm flex-col gap-6">
        <Link to="/" aria-label="knowdown — home" className="self-center">
          <Logo size={40} />
        </Link>

        <div className="flex flex-col gap-1 text-center">
          <h1 className="font-display text-2xl font-bold text-chalk">{title}</h1>
          {subtitle && <p className="text-sm text-ash">{subtitle}</p>}
        </div>

        {children}

        {footer && <div className="text-center text-sm text-ash">{footer}</div>}
      </div>
    </div>
  )
}
