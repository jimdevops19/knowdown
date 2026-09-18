import { Link, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, EyeOff } from 'lucide-react'
import { Card } from '../components/Card'
import { LevelChip } from '../components/LevelChip'
import { StatusBadge } from '../components/StatusBadge'
import { ErrorState, Loading } from '../components/states'
import { queryKeys } from '../lib/query/queryClient'
import { useTesterAccess } from '../features/tester/useTesterAccess'
import { getTesterRehearsal } from '../features/tester/api'
import { Rehearsal } from '../features/tester/Rehearsal'
import { TesterUnavailable } from '../features/tester/TesterUnavailable'

/*
 * `/tester/:type/:id` — one question, played on its own.
 *
 * A route of its own rather than a panel inside the catalog, for one reason
 * that outweighs the extra file: **it is a link somebody can send**. "This
 * question grades wrong" is a sentence that needs a URL after it, and a
 * maintainer pasting one to another maintainer is the normal way this page gets
 * used a second time.
 *
 * The URL carries the `(type, id)` pair, which is how a question is named
 * everywhere in this platform — the same pair `MatchupQuestion` stores and
 * `QuestionRef` stands for — rather than the slug. A slug is the readable name
 * and it is unique only by the loader's own check; the pair is unique by
 * construction, and it is what the catalog already holds.
 *
 * The header here is the catalog card's top half, restated: type, band,
 * category, live-or-not, slug. It is the *identity* of the question, and it
 * stays above the simulation while the board below it is replayed, reshuffled
 * and answered — so there is never a moment where a maintainer is looking at a
 * board and cannot tell which row it came out of.
 */
export function TesterQuestionPage() {
  const { questionType = '', questionId = '' } = useParams()
  const access = useTesterAccess()

  const rehearsal = useQuery({
    // Seeded by the server's own default, so the board order is stable across
    // reloads; `Rehearsal` re-deals by asking for a new one itself rather than
    // through this query, which is why the key's seed is fixed here.
    queryKey: queryKeys.tester.rehearsal(questionType, questionId, 'default'),
    queryFn: () => getTesterRehearsal(questionType, questionId),
    enabled: access.available && !!questionType && !!questionId,
    // A question does not change while it is being rehearsed, and a background
    // refetch mid-answer would swap the board out from under the clock.
    staleTime: Infinity,
    refetchOnMount: false,
  })

  if (access.isLoading) return <Loading label="Checking access…" />
  if (!access.available) return <TesterUnavailable />
  if (rehearsal.isLoading) return <Loading label="Staging the question…" />
  if (rehearsal.isError) return <ErrorState error={rehearsal.error} />
  if (!rehearsal.data) return null

  const question = rehearsal.data

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-4">
      <Link
        to="/tester"
        className="flex w-fit items-center gap-1.5 text-sm text-ash hover:text-chalk"
      >
        <ArrowLeft size={15} aria-hidden />
        All questions
      </Link>

      <Card className="flex flex-col gap-3 p-4">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-display text-[10px] font-bold uppercase tracking-[0.12em] text-volt">
            {question.type}
          </span>
          <LevelChip level={question.level} />
          <StatusBadge>{question.category_name}</StatusBadge>
          {!question.is_active && (
            <StatusBadge tone="off" className="inline-flex items-center gap-1">
              <EyeOff size={11} aria-hidden />
              Inactive
            </StatusBadge>
          )}
        </div>
        <code className="break-all font-mono text-xs text-ash">{question.slug}</code>
        {/* The resolved clock, not the authored override — this is what a
            matchup would actually give it, including the type's default when
            the author set nothing. */}
        <p className="nums text-xs text-ash">
          {question.time_limit_ms / 1000}s on the clock, after a{' '}
          {question.read_delay_ms / 1000}s read · board seed{' '}
          <span className="font-mono">{question.seed}</span>
        </p>
      </Card>

      {/* Keyed on the question, so moving between two questions starts the
          second one from nothing: a fresh clock, an unplayed board, no verdict
          and no clues from the one before. `Rehearsal` holds half a dozen
          pieces of state that all have to reset together, and a remount resets
          them by construction rather than by an effect that has to remember
          each one. */}
      <Rehearsal key={`${question.type}:${question.id}`} rehearsal={question} />
    </div>
  )
}
