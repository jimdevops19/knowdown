import { Link, useParams, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, ChevronLeft, ChevronRight, EyeOff } from 'lucide-react'
import { Button } from '../components/Button'
import { Card } from '../components/Card'
import { LevelChip } from '../components/LevelChip'
import { StatusBadge } from '../components/StatusBadge'
import { ErrorState, Loading } from '../components/states'
import { queryKeys } from '../lib/query/queryClient'
import { useTesterAccess } from '../features/tester/useTesterAccess'
import { getTesterRehearsal, listTesterQuestions } from '../features/tester/api'
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
 *
 * ## Previous / Next walk the catalog's own filtration, not the whole thing
 *
 * The URL carries the filter bar's state as a query string
 * (`QuestionCatalogCard`'s `filterQuery`) — search, category, answer shape,
 * band, "added since", "include inactive" — the same names `TesterPage`'s
 * `query` state uses, so this page can rebuild the exact filters that put this
 * question on screen and ask the catalog for that set again, ordered the same
 * way. Reviewing the fifty questions a sync just wrote is then a rehearsal
 * plus two keystrokes, never a trip back to `/tester` to click the next card.
 *
 * Arriving with no query string (a pasted `/tester/:type/:id` link, or the
 * "New question" flow, which never sets one) means there is nothing to walk —
 * so no request is made and neither button is drawn, rather than either one
 * offering to page through the *entire* catalog.
 */
export function TesterQuestionPage() {
  const { questionType = '', questionId = '' } = useParams()
  const [searchParams] = useSearchParams()
  const access = useTesterAccess()
  const config = access.config

  const hasFilters = searchParams.toString().length > 0
  const level = searchParams.get('level') ?? ''
  const selectedLevel = config?.levels.find((entry) => entry.value === level)

  // Mirrors `TesterPage`'s own `filters`, rebuilt from the query string rather
  // than from component state that page never carries. `page_size` covers the
  // backend's max (`DefaultPagination.max_page_size`) — this is a walk, not a
  // paginated list, so it asks for everything the filtration matches in one
  // request rather than reconstructing a page number that means nothing here.
  const siblings = useQuery({
    queryKey: queryKeys.tester.questions({ ...Object.fromEntries(searchParams), page_size: 100 }),
    queryFn: () =>
      listTesterQuestions({
        search: searchParams.get('search') ?? undefined,
        category: searchParams.get('category') ?? undefined,
        type: searchParams.get('type') ?? undefined,
        level_min: selectedLevel?.level_min,
        level_max: selectedLevel?.level_max,
        include_inactive: searchParams.get('includeInactive') !== 'false',
        created_after: searchParams.get('createdAfter') ?? undefined,
        page_size: 100,
      }),
    enabled: access.available && hasFilters,
    staleTime: Infinity,
  })

  const siblingRows = siblings.data?.results ?? []
  const currentIndex = siblingRows.findIndex(
    (row) => row.type === questionType && row.id === questionId,
  )
  const previousQuestion = currentIndex > 0 ? siblingRows[currentIndex - 1] : null
  const nextQuestion =
    currentIndex >= 0 && currentIndex < siblingRows.length - 1
      ? siblingRows[currentIndex + 1]
      : null

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
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Link
          to="/tester"
          className="flex w-fit items-center gap-1.5 text-sm text-ash hover:text-chalk"
        >
          <ArrowLeft size={15} aria-hidden />
          All questions
        </Link>

        {/* Walking the filtered set this question was opened from. Absent
            when the URL carries no filtration (nothing to walk) or once the
            catalog has loaded and this question sits at either end of it. */}
        {hasFilters && siblingRows.length > 0 && (
          <div className="flex items-center gap-2">
            {currentIndex >= 0 && (
              <span className="nums text-xs text-ash">
                {currentIndex + 1} of {siblingRows.length}
              </span>
            )}
            {/* A disabled `<a>` still navigates — the browser has no such
                state for one — so an end of the list renders a real `<button
                disabled>` instead of a `Link` to nowhere. */}
            {previousQuestion ? (
              <Button
                as={Link}
                to={`/tester/${previousQuestion.type}/${previousQuestion.id}?${searchParams.toString()}`}
                variant="secondary"
                size="sm"
              >
                <ChevronLeft size={14} aria-hidden />
                Previous
              </Button>
            ) : (
              <Button variant="secondary" size="sm" disabled>
                <ChevronLeft size={14} aria-hidden />
                Previous
              </Button>
            )}
            {nextQuestion ? (
              <Button
                as={Link}
                to={`/tester/${nextQuestion.type}/${nextQuestion.id}?${searchParams.toString()}`}
                variant="secondary"
                size="sm"
              >
                Next
                <ChevronRight size={14} aria-hidden />
              </Button>
            ) : (
              <Button variant="secondary" size="sm" disabled>
                Next
                <ChevronRight size={14} aria-hidden />
              </Button>
            )}
          </div>
        )}
      </div>

      <Card className="flex flex-col gap-3 p-4">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-display text-[10px] font-bold uppercase tracking-[0.12em] text-volt">
            {question.type}
          </span>
          <LevelChip level={question.level} showLabel />
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
            matchup would actually give it, including the fallback when neither
            the entry nor its resource file named one. */}
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
