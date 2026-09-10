import { useState, type FormEvent } from 'react'
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '../features/auth/useAuth'
import { useAuthConfig } from '../features/auth/useAuthConfig'
import { AuthLayout } from '../features/auth/AuthLayout'
import { Button } from '../components/Button'
import { Field } from '../components/Field'
import { Input } from '../components/Input'
import { fieldErrors, normalizeApiError } from '../lib/api/errors'

/*
 * `/register` — an email, a password, and that is the whole form.
 *
 * **No display name here.** The account arrives with a generated one, flagged
 * `player_name_is_auto`, and `/welcome` is the second half of signing up. Two
 * reasons that split is worth a page: the name has its own rules and its own
 * live availability check, and it is published on every scoreboard — so it must
 * never be seeded from the email address, not even its local part. Asking for
 * both on one screen is how a form ends up "helpfully" prefilling the name from
 * the address and publishing half of somebody's credential.
 *
 * Unlike sign-in, this form *does* show per-field errors: there is no oracle to
 * protect here — the server will refuse a taken address either way, and refusing
 * it vaguely would just make the refusal harder to act on. The password rules
 * come from the server too (`details.password1`), so this page has no copy of
 * them to drift from.
 */
export function RegisterPage() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const { register, isAuthenticated } = useAuth()
  const { passwordEnabled } = useAuthConfig()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [general, setGeneral] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  const next = params.get('next') ?? '/'

  if (isAuthenticated) return <Navigate to={next} replace />

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    setPending(true)
    setErrors({})
    setGeneral(null)
    try {
      await register(email, password)
      // Straight to the second half. `replace`, so Back from /welcome doesn't
      // land on a sign-up form for an account that now exists.
      navigate(`/welcome?next=${encodeURIComponent(next)}`, { replace: true })
    } catch (caught) {
      const error = normalizeApiError(caught)
      const perField = fieldErrors(error)
      setErrors(perField)
      // Only when nothing landed on a field, so a refusal is never shown twice.
      if (Object.keys(perField).length === 0) setGeneral(error.message)
    } finally {
      setPending(false)
    }
  }

  if (!passwordEnabled) {
    return (
      <AuthLayout title="Create an account">
        <p className="text-center text-sm text-ash">
          This deployment doesn't offer email sign-up.
        </p>
      </AuthLayout>
    )
  }

  return (
    <AuthLayout
      title="Create an account"
      subtitle="Two fields. You'll pick your name on the next screen."
    >
      <form className="flex flex-col gap-4" onSubmit={onSubmit}>
        <Field
          label="Email"
          error={errors.email}
          hint="Your login, and the only way back in if you forget your password."
        >
          <Input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoComplete="email"
            inputMode="email"
            placeholder="you@example.com"
            invalid={!!errors.email}
          />
        </Field>

        <Field
          label="Password"
          // The server's own rules, verbatim, when it refuses. Nothing is
          // duplicated here — the hint below is the shape, not the rule.
          error={errors.password1 ?? errors.password2}
          hint="At least 8 characters, with one that isn't a letter or a number."
        >
          <Input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            autoComplete="new-password"
            invalid={!!(errors.password1 ?? errors.password2)}
          />
        </Field>

        {general && (
          <p role="alert" className="text-sm text-wrong">
            {general}
          </p>
        )}

        <Button type="submit" size="full" disabled={pending}>
          {pending ? 'Creating…' : 'Create account'}
        </Button>
      </form>

      <p className="text-center text-sm text-ash">
        Already have one?{' '}
        <Link to={`/login?next=${encodeURIComponent(next)}`} className="text-volt hover:underline">
          Sign in
        </Link>
      </p>
    </AuthLayout>
  )
}
