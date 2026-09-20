import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { useAuth } from '../features/auth/useAuth'
import { DisplayNameField } from '../features/players/DisplayNameField'
import { MascotPicker } from '../features/players/MascotPicker'
import { Avatar } from '../components/Avatar'
import { Button } from '../components/Button'
import { Card } from '../components/Card'
import { SectionHeading } from '../components/SectionHeading'
import { useToast } from '../hooks/useToast'
import { normalizeApiError } from '../lib/api/errors'

/*
 * `/me` — the two things a player owns about themselves: their name and their
 * avatar, plus (read-only) the address they sign in with.
 *
 * Two separate forms rather than one save button, because they are separate
 * writes on the backend and failing them as a unit would be a lie:
 * `set_display_name` and `set_mascot` are different services. The email lives
 * on the User rather than the Player at all, and is fixed at signup — it has
 * no form of its own.
 *
 * This is also the second home of the "pick a name" prompt — the account is
 * fully usable with the generated one, so anyone who skipped `/welcome` finds
 * it here rather than being nagged into it.
 */
export function MePage() {
  const { user, needsDisplayName } = useAuth()

  return (
    <div className="flex flex-col gap-6">
      <h1 className="font-display text-2xl font-bold text-chalk">Your profile</h1>

      {needsDisplayName && (
        <Card border="border-volt/40" className="flex flex-col gap-2 p-4">
          <p className="text-sm text-chalk">
            You're still called <span className="font-semibold">{user?.player_name}</span>.
          </p>
          <p className="text-sm text-ash">
            That's the placeholder the account was created with. It works fine — it's just not
            yours.
          </p>
        </Card>
      )}

      <AvatarSection />
      <NameSection />
      <EmailSection />

      {user?.player_name && (
        <Link
          to={`/players/${user.player_name}`}
          className="text-center text-sm text-volt hover:underline"
        >
          See your public profile →
        </Link>
      )}
    </div>
  )
}

function AvatarSection() {
  const { user, updateMascot } = useAuth()
  const toast = useToast()
  const queryClient = useQueryClient()
  const [pending, setPending] = useState(false)

  /*
   * Saved on the tap, with no confirm step. The write is one short field, it is
   * trivially reversible by picking another one, and a "Save" button under a
   * grid of forty animals would mean a player who picked a raptor and walked
   * away is still wearing nothing.
   */
  async function choose(mascot: string | null) {
    if (mascot === (user?.player_mascot ?? null)) return
    setPending(true)
    try {
      await updateMascot(mascot)
      // The mark rides on every payload that carries a player, so a ladder or
      // a profile already fetched is now showing the old one.
      void queryClient.invalidateQueries({ queryKey: ['players'] })
      void queryClient.invalidateQueries({ queryKey: ['rankings'] })
      toast.success(mascot ? 'Avatar updated' : 'Back to your initials')
    } catch (caught) {
      toast.error('Could not change your avatar', {
        description: normalizeApiError(caught).message,
      })
    } finally {
      setPending(false)
    }
  }

  return (
    <section className="flex flex-col gap-3">
      <SectionHeading>Avatar</SectionHeading>
      <Card className="flex items-center gap-4 p-4">
        {/* The real `Avatar`, not the mark on its own: it is what resolves a
            mascot down to initials, so the preview is the thing everybody else
            sees rather than a second opinion about it. */}
        <Avatar
          name={user?.player_name ?? '?'}
          seed={user?.player_id ?? undefined}
          mascot={user?.player_mascot ?? null}
          size={64}
        />
        <div className="flex flex-1 flex-col items-start gap-1">
          <MascotPicker
            value={user?.player_mascot ?? null}
            onChange={(mascot) => void choose(mascot)}
            disabled={pending}
          />
        </div>
      </Card>
      <p className="text-xs text-ash/70">
        {/* There is nothing to upload and nothing to explain about file sizes:
            the marks ship with the app, so the only thing worth saying is what
            happens if you pick none of them. */}
        Shown wherever you appear. Pick none and you get your initials on a
        colour of your own, generated from your name.
      </p>
    </section>
  )
}

function NameSection() {
  const { user, updateDisplayName } = useAuth()
  const queryClient = useQueryClient()
  const toast = useToast()
  const [name, setName] = useState('')
  const [error, setError] = useState<string | undefined>()
  const [pending, setPending] = useState(false)

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    setPending(true)
    setError(undefined)
    const previous = user?.player_name
    try {
      await updateDisplayName(name.trim())
      // The old name's profile cache is now a 404 and the new one is unfetched;
      // drop the whole namespace rather than reasoning about which keys moved.
      void queryClient.invalidateQueries({ queryKey: ['players'] })
      void queryClient.invalidateQueries({ queryKey: ['rankings'] })
      toast.success(`You're now ${name.trim()}`, {
        description: previous ? `Previously ${previous}.` : undefined,
      })
      setName('')
    } catch (caught) {
      setError(normalizeApiError(caught).message)
    } finally {
      setPending(false)
    }
  }

  return (
    <section className="flex flex-col gap-3">
      <SectionHeading>Display name</SectionHeading>
      <Card className="p-4">
        <form className="flex flex-col gap-4" onSubmit={onSubmit}>
          <p className="text-sm text-ash">
            Currently <span className="font-semibold text-chalk">{user?.player_name}</span>.
          </p>
          <DisplayNameField
            label="New name"
            value={name}
            onChange={setName}
            currentName={user?.player_name}
            serverError={error}
          />
          <Button type="submit" disabled={pending || name.trim().length < 3} className="self-start">
            {pending ? 'Saving…' : 'Change name'}
          </Button>
        </form>
      </Card>
    </section>
  )
}

function EmailSection() {
  const { user } = useAuth()

  return (
    <section className="flex flex-col gap-3">
      <SectionHeading>Sign-in email</SectionHeading>
      <Card className="p-4">
        <p className="text-sm text-ash">
          {/* This is the one screen in the whole app where an email address
              appears — `/auth/me/` is the only endpoint allowed to emit one,
              and nothing else fetches it. It's fixed at signup and cannot be
              changed here. */}
          <span className="font-semibold text-chalk">{user?.email ?? 'not set'}</span>. Nobody
          else can see it, and it can't be changed.
        </p>
      </Card>
    </section>
  )
}
