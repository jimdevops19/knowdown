import { useState, type FormEvent } from 'react'
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '../features/auth/useAuth'
import { useAuthConfig } from '../features/auth/useAuthConfig'
import { AuthLayout } from '../features/auth/AuthLayout'
import { Button } from '../components/Button'
import { Field } from '../components/Field'
import { Input } from '../components/Input'
import { normalizeApiError } from '../lib/api/errors'

/*
 * `/login`.
 *
 * **One error line, never two.** The server refuses a wrong password, an
 * unknown address and a malformed one identically — and hashes against a dummy
 * even for an address it has never seen, so the refusal cannot be told apart by
 * how long it takes. A form that said "no account with that email" would
 * rebuild the account-existence oracle the backend went to that trouble to
 * remove, so there is exactly one message here and it covers both fields.
 *
 * The lockout is the same shape: repeated failures earn a 429 with a
 * `Retry-After`, counted per *address typed* rather than per account found. Its
 * message comes from the server for the same reason — the client does not know,
 * and must not appear to know, whether the address it just locked out exists.
 */
export function LoginPage() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const { login, isAuthenticated } = useAuth()
  const { passwordEnabled } = useAuthConfig()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  // Where to go once signed in. Carried from wherever the guard bounced them,
  // so somebody who tapped a link into a live match lands on the match.
  const next = params.get('next') ?? '/'

  if (isAuthenticated) return <Navigate to={next} replace />

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    setPending(true)
    setError(null)
    try {
      await login(email, password)
      navigate(next, { replace: true })
    } catch (caught) {
      setError(normalizeApiError(caught).message)
    } finally {
      setPending(false)
    }
  }

  return (
    <AuthLayout title="Welcome back" subtitle="Sign in and get back in the pool.">
      {passwordEnabled ? (
        <form className="flex flex-col gap-4" onSubmit={onSubmit}>
          <Field label="Email">
            <Input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="email"
              // `username` is the right autocomplete token even though the
              // credential is an email — it is what a password manager keys the
              // saved entry on, and getting it wrong means saved logins never
              // offer themselves.
              inputMode="email"
              placeholder="you@example.com"
              invalid={!!error}
            />
          </Field>

          <Field label="Password">
            <Input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="current-password"
              invalid={!!error}
            />
          </Field>

          {/* One line, covering both fields — see the note at the top. */}
          {error && (
            <p role="alert" className="text-sm text-wrong">
              {error}
            </p>
          )}

          <Button type="submit" size="full" disabled={pending}>
            {pending ? 'Signing in…' : 'Sign in'}
          </Button>

          <Link to="/forgot-password" className="text-center text-sm text-volt hover:underline">
            Forgot your password?
          </Link>
        </form>
      ) : (
        // A tier with no password door leaves those routes unmounted, so the
        // form would post into a 404. Say so rather than showing one.
        <p className="text-center text-sm text-ash">
          This deployment doesn't offer email sign-in.
        </p>
      )}

      <p className="text-center text-sm text-ash">
        New here?{' '}
        <Link
          to={`/register?next=${encodeURIComponent(next)}`}
          className="text-volt hover:underline"
        >
          Create an account
        </Link>
      </p>
    </AuthLayout>
  )
}
