import { useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { Search, Wrench } from 'lucide-react'
import { Button } from '../components/Button'
import { Card } from '../components/Card'
import { Input } from '../components/Input'
import { EmptyState, ErrorState, Loading } from '../components/states'
import { queryKeys } from '../lib/query/queryClient'
import { useDebouncedValue } from '../hooks/useDebouncedValue'
import { useTesterAccess } from '../features/tester/useTesterAccess'
import { listTesterQuestions } from '../features/tester/api'
import { QuestionCatalogCard } from '../features/tester/QuestionCard'
import { TesterUnavailable } from '../features/tester/TesterUnavailable'

/*
 * `/tester` — every question in the database, searchable, one card each.
 *
 * The maintainers' page. Not linked from anywhere a player can see it, not
 * mounted on a tier that did not ask for it, and refused by the backend for any
 * account that is not `is_staff` — `useTesterAccess` asks all of that in one
 * request, and until it answers this page draws nothing rather than guessing.
 *
 * ## What the filters are for
 *
 * A maintainer arrives here having just edited a YAML file, and is looking for
 * one question out of the catalog. Search covers the three things they might
 * remember about it — its slug, its wording, or its sport — and the selects
 * cover the ways they might narrow it instead ("the grids", "the F1 ones",
 * "the hard ones").
 * Everything is a query parameter on one endpoint, so the filters compose and
 * none of the narrowing happens in this browser.
 *
 * ## Inactive questions are shown by default
 *
 * The one place this page deliberately disagrees with every other list in the
 * app. Matchmaking cannot draw a deactivated question, so a player never sees
 * one — and "why does this question never come up?" is one of the two or three
 * things somebody opens this page to find out. Hiding them by default would
 * answer that question with an empty result, which is the least useful possible
 * answer.
 */
export function TesterPage() {
  const access = useTesterAccess()

  /*
   * Every filter and the page number in one piece of state, changed through one
   * setter — because **any change of filter has to reset the page**, and that
   * is a rule about the pair rather than about either half. Narrowing a search
   * while on page three would otherwise ask for page three of a one-page
   * result, which comes back empty and reads as "nothing matches" for a search
   * that has plenty.
   *
   * The obvious spelling — a `useState` each, plus an effect that resets the
   * page when any of them changes — is a render that sets state to correct the
   * render before it, with a request already in flight for the page it is about
   * to abandon. Keeping them together makes the rule structural: there is no
   * way to set a filter *without* setting the page, because it is one write.
   */
  const [query, setQuery] = useState({
    search: '',
    category: '',
    type: '',
    level: '',
    includeInactive: true,
    page: 1,
  })

  function narrow(change: Partial<Omit<typeof query, 'page'>>) {
    setQuery((current) => ({ ...current, ...change, page: 1 }))
  }

  // A keystroke is not a request — the same reason the display-name field
  // debounces. The typed value is what the box shows; the settled one is what
  // the catalog is asked for.
  const settledSearch = useDebouncedValue(query.search)

  const config = access.config

  // The band the dropdown names ("medium") is not itself a filter the
  // backend understands — the catalog filters on `level_min`/`level_max`, so
  // the band is resolved to the range `config` says it covers before it goes
  // on the request. Nothing to resolve while `config` hasn't loaded yet: the
  // select renders empty until then, so `query.level` cannot be set.
  const selectedLevel = config?.levels.find((entry) => entry.value === query.level)

  const filters = {
    search: settledSearch,
    category: query.category,
    type: query.type,
    level_min: selectedLevel?.level_min,
    level_max: selectedLevel?.level_max,
    include_inactive: query.includeInactive,
    page: query.page,
  }

  const questions = useQuery({
    queryKey: queryKeys.tester.questions(filters),
    queryFn: () => listTesterQuestions(filters),
    enabled: access.available,
    // The list is the page's whole content; without this it blanks out and
    // re-flows on every keystroke that survives the debounce.
    placeholderData: keepPreviousData,
  })

  if (access.isLoading) return <Loading label="Checking access…" />
  if (!access.available) return <TesterUnavailable />

  const rows = questions.data?.results ?? []
  const pagination = questions.data?.pagination
  // The backend's own names for the eight answer shapes, rather than a second
  // copy of them maintained here — the registry is over there and this page
  // only borrows its labels.
  const typeLabels = new Map((config?.types ?? []).map((entry) => [entry.value, entry.label]))

  return (
    <div className="flex flex-col gap-5">
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <h1 className="flex items-center gap-2.5 font-display text-2xl font-bold text-chalk">
          <Wrench size={20} className="text-volt" aria-hidden />
          Question tester
        </h1>
        <p className="nums text-sm text-ash">
          {config?.question_count ?? 0} in the catalog
        </p>
      </header>

      <Card className="flex flex-col gap-3 p-4">
        <label className="relative flex items-center">
          <Search size={16} className="absolute left-3 text-ash" aria-hidden />
          <Input
            size="sm"
            className="pl-9"
            value={query.search}
            onChange={(event) => narrow({ search: event.target.value })}
            placeholder="Search a slug, the question text, or a sport"
            aria-label="Search questions"
          />
        </label>

        <div className="flex flex-wrap items-center gap-2">
          <Select
            label="Category"
            value={query.category}
            onChange={(category) => narrow({ category })}
            options={[
              { value: '', label: 'Every category' },
              ...(config?.categories ?? []).map((entry) => ({
                value: entry.slug,
                label: `${entry.name} (${entry.question_count})`,
              })),
            ]}
          />
          <Select
            label="Answer shape"
            value={query.type}
            onChange={(type) => narrow({ type })}
            options={[
              { value: '', label: 'Every answer shape' },
              ...(config?.types ?? []).map((entry) => ({
                value: entry.value,
                label: `${entry.label} (${entry.question_count})`,
              })),
            ]}
          />
          <Select
            label="Difficulty"
            value={query.level}
            onChange={(level) => narrow({ level })}
            options={[
              { value: '', label: 'Every difficulty' },
              ...(config?.levels ?? []).map((entry) => ({
                value: entry.value,
                label: `${entry.label} (${entry.question_count})`,
              })),
            ]}
          />
          <label className="flex cursor-pointer items-center gap-2 text-sm text-ash">
            <input
              type="checkbox"
              checked={query.includeInactive}
              onChange={(event) => narrow({ includeInactive: event.target.checked })}
              className="h-4 w-4 accent-court"
            />
            Include inactive
          </label>
        </div>
      </Card>

      {questions.isLoading && <Loading variant="cards" />}
      {questions.isError && <ErrorState error={questions.error} />}
      {questions.data && rows.length === 0 && (
        <EmptyState message="No question matches those filters." />
      )}

      <div className="grid gap-3 sm:grid-cols-2 desk:grid-cols-3">
        {rows.map((question) => (
          <QuestionCatalogCard
            key={`${question.type}:${question.id}`}
            question={question}
            typeLabel={typeLabels.get(question.type) ?? question.type}
          />
        ))}
      </div>

      {pagination && pagination.pages > 1 && (
        <div className="flex items-center justify-between gap-3">
          <Button
            variant="secondary"
            size="sm"
            disabled={!pagination.previous}
            onClick={() => setQuery((current) => ({ ...current, page: current.page - 1 }))}
          >
            Previous
          </Button>
          <span className="nums text-sm text-ash">
            Page {pagination.page} of {pagination.pages} · {pagination.count} questions
          </span>
          <Button
            variant="secondary"
            size="sm"
            disabled={!pagination.next}
            onClick={() => setQuery((current) => ({ ...current, page: current.page + 1 }))}
          >
            Next
          </Button>
        </div>
      )}
    </div>
  )
}

/** A plain select, styled to match `Input`. Not promoted to `components/`: this
 *  is the only screen in the app with a dropdown on it, and a shared component
 *  with one caller is a layer that has not earned its name. */
function Select({
  label,
  value,
  onChange,
  options,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  options: { value: string; label: string }[]
}) {
  return (
    <select
      aria-label={label}
      value={value}
      onChange={(event) => onChange(event.target.value)}
      className="h-11 rounded-input border border-chalk/8 bg-raised px-3 text-sm text-chalk outline-none transition-all duration-150 focus:border-volt focus:ring-2 focus:ring-volt/25"
    >
      {options.map((option) => (
        <option key={option.value} value={option.value} className="bg-raised">
          {option.label}
        </option>
      ))}
    </select>
  )
}
