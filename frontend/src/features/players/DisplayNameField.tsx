import { useQuery } from '@tanstack/react-query'
import { Check, Loader2, X } from 'lucide-react'
import { checkDisplayName } from '../../lib/api/endpoints'
import { queryKeys } from '../../lib/query/queryClient'
import { useDebouncedValue } from '../../hooks/useDebouncedValue'
import { Field } from '../../components/Field'
import { Input } from '../../components/Input'

/*
 * The one field a player fills in about themselves, with the server's own
 * verdict beside it.
 *
 * **Every rule about the name is the server's**, and none of them are
 * re-implemented here. `GET /players/display-name-available/` answers with the
 * refusal code *and the message the PATCH would have given*, so the field shows
 * the real reason — taken, invalid, reserved — before anybody presses save. A
 * client-side copy of "3-30 characters, letters, numbers and underscores, not
 * `admin`" would be a second source of truth that drifts the day the reserved
 * list grows, and would be wrong in the direction that matters: refusing a name
 * the server would have allowed.
 *
 * The one thing mirrored locally is `maxLength`, because a field that lets you
 * type 60 characters and then refuses them is worse than one that stops at 30.
 *
 * The check is debounced, so a keystroke is not a request. It also only fires
 * once there is something worth asking about, and never for the name the player
 * already has — renaming yourself to your own current name is legal (the
 * uniqueness constraint is case-insensitive, so changing your own
 * capitalisation is a real thing to want), and asking would report it "taken".
 */
export function DisplayNameField({
  value,
  onChange,
  currentName,
  label = 'Display name',
  serverError,
}: {
  value: string
  onChange: (value: string) => void
  /** The name the player already holds, if any — never checked against. */
  currentName?: string | null
  label?: string
  /** A refusal from a submit that already happened, which outranks the check. */
  serverError?: string
}) {
  const settled = useDebouncedValue(value.trim())
  const worthAsking =
    settled.length >= 3 && settled.toLowerCase() !== (currentName ?? '').toLowerCase()

  const availability = useQuery({
    queryKey: queryKeys.players.nameAvailable(settled),
    queryFn: () => checkDisplayName(settled),
    enabled: worthAsking,
    // The answer is about a name, not about this player, and it can change
    // under you — somebody else may claim it in the seconds you spend deciding.
    // Short-lived on purpose; the real arbiter is the PATCH and the constraint
    // beneath it.
    staleTime: 10_000,
    retry: false,
  })

  const answer = worthAsking ? availability.data : undefined
  const checking = worthAsking && availability.isFetching
  const taken = answer && !answer.available

  return (
    <Field
      label={label}
      error={serverError ?? (taken ? (answer.message ?? 'That name is taken.') : undefined)}
      hint={
        answer?.available ? (
          <span className="flex items-center gap-1 text-correct">
            <Check size={13} aria-hidden />
            {answer.display_name} is free
          </span>
        ) : (
          'This is the name on every scoreboard. Not your login — you sign in with your email.'
        )
      }
    >
      <div className="relative">
        <Input
          value={value}
          onChange={(event) => onChange(event.target.value)}
          maxLength={30}
          placeholder="e.g. courtvision"
          autoComplete="off"
          autoCorrect="off"
          autoCapitalize="off"
          spellCheck={false}
          invalid={!!serverError || !!taken}
          className="pr-11"
        />
        <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center">
          {checking ? (
            <Loader2 size={17} className="animate-spin text-ash" aria-label="Checking…" />
          ) : answer?.available ? (
            <Check size={17} className="text-correct" aria-hidden />
          ) : taken ? (
            <X size={17} className="text-wrong" aria-hidden />
          ) : null}
        </span>
      </div>
    </Field>
  )
}
