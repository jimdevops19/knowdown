import { useState, type FormEvent } from 'react'
import { Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '../features/auth/useAuth'
import { AuthLayout } from '../features/auth/AuthLayout'
import { DisplayNameField } from '../features/players/DisplayNameField'
import { Button } from '../components/Button'
import { normalizeApiError } from '../lib/api/errors'
import { Loading } from '../components/states'

/*
 * `/welcome` — the second half of signing up: pick the name that goes on every
 * scoreboard.
 *
 * A page of its own rather than a step in the register form, because the name
 * has rules the address doesn't, a live availability check, and one property
 * that has to be structurally true: **it is never derived from the email**. The
 * account arrives named `player_7`, not `jim`, and this is where a person
 * replaces that with something they chose.
 *
 * **Nothing is blocked behind it.** The account is fully usable with the
 * generated name — you can play, win, and appear on the ladder as `player_7` —
 * so "Skip for now" is a real option and not a dark pattern in reverse. The
 * prompt reappears on the profile page for anyone who leaves without answering.
 *
 * Somebody who has already chosen is redirected away: this URL is a doorway,
 * and a doorway you can walk back through after the fact is a rename form
 * pretending to be onboarding. Renaming lives on `/me`.
 */
export function ChooseNamePage() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const { user, status, needsDisplayName, updateDisplayName } = useAuth()

  const [name, setName] = useState('')
  const [error, setError] = useState<string | undefined>()
  const [pending, setPending] = useState(false)

  const next = params.get('next') ?? '/'

  if (status === 'loading') return <Loading label="One moment…" />
  if (status !== 'authenticated') return <Navigate to="/login" replace />
  if (!needsDisplayName) return <Navigate to={next} replace />

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    setPending(true)
    setError(undefined)
    try {
      await updateDisplayName(name.trim())
      navigate(next, { replace: true })
    } catch (caught) {
      // The claim is settled here, not by the availability check beside the
      // field: two people can be typing the same name at once, and the database
      // constraint is what decides between them. A `conflict` at this point is
      // that race, and the message says so.
      setError(normalizeApiError(caught).message)
    } finally {
      setPending(false)
    }
  }

  return (
    <AuthLayout
      title="Pick your name"
      subtitle={
        <>
          You're signed in as <span className="text-chalk">{user?.player_name}</span>. That's a
          placeholder — choose something you'd rather see on the ladder.
        </>
      }
    >
      <form className="flex flex-col gap-4" onSubmit={onSubmit}>
        <DisplayNameField
          value={name}
          onChange={setName}
          currentName={user?.player_name}
          serverError={error}
        />

        <Button type="submit" size="full" disabled={pending || name.trim().length < 3}>
          {pending ? 'Claiming…' : 'Claim it'}
        </Button>

        <Button variant="ghost" size="full" onClick={() => navigate(next, { replace: true })}>
          Skip for now
        </Button>
      </form>
    </AuthLayout>
  )
}
