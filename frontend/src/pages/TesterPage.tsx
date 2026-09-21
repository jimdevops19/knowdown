import { useEffect, useState } from 'react'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus, Search, Wrench } from 'lucide-react'
import { Button } from '../components/Button'
import { Card } from '../components/Card'
import { Input } from '../components/Input'
import { EmptyState, ErrorState, Loading } from '../components/states'
import { queryKeys } from '../lib/query/queryClient'
import { useDebouncedValue } from '../hooks/useDebouncedValue'
import { useToast } from '../hooks/useToast'
import { useTesterAccess } from '../features/tester/useTesterAccess'
import {
  getTesterQuestionSource,
  listTesterQuestions,
  setTesterQuestionActive,
} from '../features/tester/api'
import { QuestionCatalogCard } from '../features/tester/QuestionCard'
import { QuestionEditor } from '../features/tester/QuestionEditor'
import { describeRefusal } from '../features/tester/entryDrafts'
import { TesterUnavailable } from '../features/tester/TesterUnavailable'
import type { TesterQuestionCard } from '../lib/api/types'

/** What the greyed verbs say on hover where this tier will not take a write.
 *  One sentence, and it names the fix rather than the rule: the person reading
 *  it has a change to make and needs to know where to go and make it. */
const LOCKED_REASON =
  "Can't edit questions in staging — do it from local so it's also saved in the questions resources' YAML files."

/** Today, in the browser's local timezone, as the `YYYY-MM-DD` the `created_after`
 *  filter and the `<input type="date">` both speak. `toISOString` would answer in
 *  UTC, which reads as yesterday for part of the evening in a timezone ahead of it. */
function todayIso(): string {
  const now = new Date()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${now.getFullYear()}-${month}-${day}`
}

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
 * ## The catalog is editable from here, and editing means editing the YAML
 *
 * "New question", "Edit" and "Retire" are three verbs over one thing: the block
 * a question is authored as in `backend/apps/questions/resources/`. None of
 * them writes a question row. Each edits the file and then runs the ordinary
 * `sync_questions` over that category, which is what loads the change — so what
 * this page produces is a change to the repository, reviewable in `git diff`
 * and safe from the next deploy's sync, rather than a row that sync would
 * silently undo. `features/tester/QuestionEditor` is where that is spelled out
 * at length, and the toast after every save names the file it touched.
 *
 * **And only where the deployment says so.** `GET /tester/config/` carries an
 * `editable` flag (`QUESTION_TESTER_EDITABLE`), true on a developer's machine
 * and false on staging, where the YAML this writes lives inside the container
 * image: the edit would vanish at the next deploy and never reach git. With it
 * false the three verbs are still drawn, greyed, saying on hover to make the
 * change from local — the backend refuses them too (`CanEditQuestions`), which
 * is the actual gate; this is only the half that explains itself.
 *
 * **Nothing here deletes.** Retiring writes `is_active: false` — a matchup that
 * already played a question points at its row, and a hard delete would edit a
 * game two people have already finished. It is the same rule the loader has
 * always followed for a question dropped from a file.
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
  const toast = useToast()
  const queryClient = useQueryClient()

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
    // "" means unset. Otherwise an ISO date, so the request and the checkbox
    // that sets it agree on what "today" means.
    createdAfter: '',
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
    created_after: query.createdAfter || undefined,
    page: query.page,
  }

  /* The same filtration, restated as a URL query string, carried onto every
   * card's link into `/tester/:type/:id`. That page has no other way to know
   * "which 50 questions was this one clicked out of" — it is a fresh route,
   * not a panel of this one — and Previous/Next there has nothing to iterate
   * over without it. `page` is left out on purpose: rehearsing question 1 of
   * page 2 should still be able to walk back into page 1's last question. */
  const filterQuery = new URLSearchParams(
    Object.entries({
      search: query.search,
      category: query.category,
      type: query.type,
      level: query.level,
      createdAfter: query.createdAfter,
      includeInactive: query.includeInactive ? '' : 'false',
    }).filter(([, value]) => value !== ''),
  ).toString()

  const questions = useQuery({
    queryKey: queryKeys.tester.questions(filters),
    queryFn: () => listTesterQuestions(filters),
    enabled: access.available,
    // The list is the page's whole content; without this it blanks out and
    // re-flows on every keystroke that survives the debounce.
    placeholderData: keepPreviousData,
  })

  /* Which question the editor is open on. `null` is closed, `'new'` is a
   * create, and a card is an edit — one piece of state rather than an `open`
   * flag beside a selection, so "open on nothing" is not a state that exists. */
  const [editing, setEditing] = useState<TesterQuestionCard | 'new' | null>(null)

  // The authored entry behind the question being edited. Fetched on demand
  // rather than with the list: it is the *file's* copy of one question, and
  // fetching fifty of them to open one would be fifty file reads per page.
  const source = useQuery({
    queryKey:
      editing && editing !== 'new'
        ? queryKeys.tester.source(editing.type, editing.id)
        : ['tester', 'source', 'none'],
    queryFn: () =>
      getTesterQuestionSource(
        (editing as TesterQuestionCard).type,
        (editing as TesterQuestionCard).id,
      ),
    enabled: editing !== null && editing !== 'new',
  })

  /* A row whose file no longer holds it — renamed in the YAML, or synced once
   * and since removed — fails that fetch, and there is then no entry for a form
   * to be seeded from. Said where the click was and the selection dropped,
   * rather than left as a panel under a three-column grid: below the fold, the
   * only thing "Edit" appears to do is nothing. The wording is the backend's
   * own — it names the file that should have held the question. */
  useEffect(() => {
    if (!source.isError) return
    toast.error('That question has no source to edit', {
      description: describeRefusal(source.error),
      duration: 0,
    })
    setEditing(null)
  }, [source.isError, source.error, toast])

  const toggleActive = useMutation({
    mutationFn: (question: TesterQuestionCard) =>
      setTesterQuestionActive(question.type, question.id, !question.is_active),
    onSuccess: (result) => {
      toast.success(result.question.is_active ? 'Question restored' : 'Question retired', {
        description: `${result.source.path} · ${result.sync.summary}`,
        duration: 6000,
      })
      void queryClient.invalidateQueries({ queryKey: ['tester'] })
    },
    onError: (error) => {
      toast.error('The catalog refused that', {
        description: describeRefusal(error),
        duration: 0,
      })
    },
  })

  if (access.isLoading) return <Loading label="Checking access…" />
  if (!access.available) return <TesterUnavailable />

  const rows = questions.data?.results ?? []
  const pagination = questions.data?.pagination
  // The backend's own names for the eight answer shapes, rather than a second
  // copy of them maintained here — the registry is over there and this page
  // only borrows its labels.
  /* Whether this deployment will accept a write at all. Absent config means
     no — the verbs appear only once the server has said they work, the same
     way the page itself waits on `access.available`. */
  const editable = config?.editable ?? false
  const typeLabels = new Map((config?.types ?? []).map((entry) => [entry.value, entry.label]))

  return (
    <div className="flex flex-col gap-5">
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <h1 className="flex items-center gap-2.5 font-display text-2xl font-bold text-chalk">
          <Wrench size={20} className="text-volt" aria-hidden />
          Question tester
        </h1>
        <div className="flex items-center gap-3">
          <p className="nums text-sm text-ash">
            {config?.question_count ?? 0} in the catalog
          </p>
          {/* `title` on the wrapper, not the button: a `disabled` control
              swallows mouse events, so its own tooltip would never open. */}
          <span title={editable ? undefined : LOCKED_REASON} className="inline-flex">
            <Button size="sm" onClick={() => setEditing('new')} disabled={!editable}>
              <Plus size={15} aria-hidden />
              New question
            </Button>
          </span>
        </div>
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
          {/* Review-a-sync filter: what got added on a given day, newest first
              (the backend sorts that way once `created_after` is set). "Today"
              is one click at the value a maintainer wants right after running
              `sync_questions`; the date field is there for any other day. */}
          <Button
            size="sm"
            variant={query.createdAfter === todayIso() ? 'primary' : 'secondary'}
            onClick={() =>
              narrow({ createdAfter: query.createdAfter === todayIso() ? '' : todayIso() })
            }
          >
            Added today
          </Button>
          <label className="flex items-center gap-2 text-sm text-ash">
            Added since
            <input
              type="date"
              value={query.createdAfter}
              onChange={(event) => narrow({ createdAfter: event.target.value })}
              className="h-11 rounded-input border border-chalk/8 bg-raised px-3 text-sm text-chalk outline-none transition-all duration-150 focus:border-volt focus:ring-2 focus:ring-volt/25"
            />
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
            filterQuery={filterQuery}
            onEdit={() => setEditing(question)}
            onToggleActive={() => toggleActive.mutate(question)}
            lockedReason={editable ? undefined : LOCKED_REASON}
            /* Both verbs go dead while this question's source is in flight —
               opening the editor is a fetch, and without this the card looks
               untouched for as long as it takes. */
            busy={
              (toggleActive.isPending && toggleActive.variables?.id === question.id) ||
              (source.isLoading && editing !== 'new' && editing?.id === question.id)
            }
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

      {/* A create needs nothing fetched; an edit waits for the file's copy of
          the question, because that — not the row — is what the form edits. */}
      {editing === 'new' && (
        <QuestionEditor config={config} onClose={() => setEditing(null)} />
      )}
      {editing && editing !== 'new' && source.data && (
        <QuestionEditor
          config={config}
          editing={{ question: editing, source: source.data }}
          onClose={() => setEditing(null)}
        />
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
