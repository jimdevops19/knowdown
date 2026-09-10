import { useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { confirmPasswordReset } from '../features/auth/api'
import { AuthLayout } from '../features/auth/AuthLayout'
import { Button } from '../components/Button'
import { Field } from '../components/Field'
import { Input } from '../components/Input'
import { fieldErrors, normalizeApiError } from '../lib/api/errors'

/*
 * `/reset-password?uid=…&token=…` — the other end of the emailed link.
 *
 * The pair in the query string is spent here, once. A bad, expired or
 * already-used pair is a 400 whose message is the server's, not this page's —
 * it is the only side that knows which of the three it was, and inventing copy
 * for it here would mean guessing.
 *
 * The link arriving without its query string at all is the one case worth
 * catching before the form: it means the link was truncated on its way through
 * an email client, and asking someone to type a new password into a form that
 * cannot submit is worse than telling them to request a fresh link.
 */
export function ResetPasswordPage() {
  const [params] = useSearchParams()
  const navigate = useNavigate()

  const uid = params.get('uid') ?? ''
  const token = params.get('token') ?? ''

  const [password, setPassword] = useState('')
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [general, setGeneral] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  if (!uid || !token) {
    return (
      <AuthLayout title="That link is incomplete">
        <p className="text-center text-sm text-ash">
          Password reset links can get cut short by email clients. Ask for a fresh one.
        </p>
        <Button as={Link} to="/forgot-password" size="full">
          Send a new link
        </Button>
      </AuthLayout>
    )
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    setPending(true)
    setErrors({})
    setGeneral(null)
    try {
      await confirmPasswordReset(uid, token, password)
      // Not signed in by this — the reset sets a password, it does not mint a
      // session. Sending them to sign in with it is the honest next step.
      navigate('/login', { replace: true })
    } catch (caught) {
      const error = normalizeApiError(caught)
      const perField = fieldErrors(error)
      setErrors(perField)
      if (Object.keys(perField).length === 0) setGeneral(error.message)
    } finally {
      setPending(false)
    }
  }

  return (
    <AuthLayout title="Set a new password">
      <form className="flex flex-col gap-4" onSubmit={onSubmit}>
        <Field
          label="New password"
          error={errors.new_password1 ?? errors.new_password2 ?? errors.token ?? errors.uid}
          hint="At least 8 characters, with one that isn't a letter or a number."
        >
          <Input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            autoComplete="new-password"
            invalid={!!(errors.new_password1 ?? errors.new_password2)}
          />
        </Field>

        {general && (
          <p role="alert" className="text-sm text-wrong">
            {general}
          </p>
        )}

        <Button type="submit" size="full" disabled={pending}>
          {pending ? 'Saving…' : 'Save and sign in'}
        </Button>
      </form>
    </AuthLayout>
  )
}
