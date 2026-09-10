import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { MailCheck } from 'lucide-react'
import { requestPasswordReset } from '../features/auth/api'
import { AuthLayout } from '../features/auth/AuthLayout'
import { Button } from '../components/Button'
import { Field } from '../components/Field'
import { Input } from '../components/Input'
import { normalizeApiError } from '../lib/api/errors'

/*
 * `/forgot-password`.
 *
 * **The confirmation is the same whatever happens.** The server answers
 * identically whether or not the address matches an account — that is the whole
 * point of the endpoint, and a screen that said "we've sent it" for a real
 * address and "no such account" for an unknown one would undo it in the one
 * place it matters most. So there is exactly one success state, and it does not
 * claim an email was sent to *that* address; it says what happens if it was.
 *
 * The only failure worth showing is the request itself failing — offline, or
 * the 429 this route's own throttle scope raises. Everything else resolves.
 */
export function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [sent, setSent] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    setPending(true)
    setError(null)
    try {
      await requestPasswordReset(email)
      setSent(true)
    } catch (caught) {
      setError(normalizeApiError(caught).message)
    } finally {
      setPending(false)
    }
  }

  if (sent) {
    return (
      <AuthLayout title="Check your inbox">
        <div className="flex flex-col items-center gap-4 text-center">
          <MailCheck size={36} className="text-correct" aria-hidden />
          <p className="text-sm text-ash">
            If <span className="text-chalk">{email}</span> has an account, a reset link is on its
            way. It expires, so use it soon.
          </p>
          <Button as={Link} to="/login" size="full" variant="secondary">
            Back to sign in
          </Button>
        </div>
      </AuthLayout>
    )
  }

  return (
    <AuthLayout
      title="Reset your password"
      subtitle="We'll email you a link to set a new one."
    >
      <form className="flex flex-col gap-4" onSubmit={onSubmit}>
        <Field label="Email">
          <Input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoComplete="email"
            inputMode="email"
            placeholder="you@example.com"
          />
        </Field>

        {error && (
          <p role="alert" className="text-sm text-wrong">
            {error}
          </p>
        )}

        <Button type="submit" size="full" disabled={pending}>
          {pending ? 'Sending…' : 'Send the link'}
        </Button>

        <Link to="/login" className="text-center text-sm text-volt hover:underline">
          Back to sign in
        </Link>
      </form>
    </AuthLayout>
  )
}
