import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { QuestionCatalogCard } from './QuestionCard'
import { QuestionEditor } from './QuestionEditor'
import { BLANK_ENTRIES, describeRefusal, pruneEntry } from './entryDrafts'
import { ToastProvider } from '../../components/Toast'
import { ApiError } from '../../lib/api/errors'
import type { TesterConfig, TesterQuestionCard, TesterQuestionSource } from '../../lib/api/types'

/*
 * The authoring half of the tester.
 *
 * What is worth testing here is the handful of places where the obvious
 * implementation would be *wrong in a way nothing would notice* — a form that
 * writes a plausible entry and a catalog that silently stops matching its
 * files. In order of how expensive the mistake is:
 *
 *  1. **An absent key is not an empty one.** In a resource file, no
 *     `time_limit_seconds` means "take the tempo this whole file sets"; a `0`
 *     or a `""` opts the question out of that. A form that sent every field it
 *     rendered would quietly detach every question anybody edited from its
 *     file's clock, and every board would look fine.
 *  2. **The form seeds from the file, not the row.** Same failure, arriving by
 *     the other road — the row has had the file's clock resolved into it.
 *  3. **The editors are a registry over `QuestionType`.** A shape with no
 *     editor is a shape nobody can author, with nothing on screen saying so.
 *  4. **Retire is not delete**, and it is a verb on the card rather than
 *     something you find by opening the question.
 *
 * What is deliberately *not* tested: whether an entry is valid. That is
 * `apps.questions.schemas`' job, it is tested there against the loader itself,
 * and asserting it here would be a second copy of the contract drifting in the
 * direction of accepting what the backend refuses.
 */

const CONFIG: TesterConfig = {
  enabled: true,
  question_count: 2,
  categories: [{ slug: 'nba', name: 'NBA', question_count: 2 }],
  types: [
    { value: 'single-answer', label: 'Single answer', question_count: 2 },
    { value: 'ordering', label: 'Ordering', question_count: 0 },
  ],
  levels: [{ value: 'easy', label: 'Easy', level_min: 1, level_max: 3, question_count: 2 }],
}

const CARD: TesterQuestionCard = {
  id: 'q-1',
  type: 'single-answer',
  slug: 'kobe-81-point-game',
  description: 'Which team did Kobe score 81 against?',
  level: 5,
  category: 'nba',
  category_name: 'NBA',
  tags: { era: '2000s' },
  is_active: true,
  // The row carries a clock. The entry below does not — the loader put this
  // there from the file, and that gap is the subject of a test.
  time_limit_seconds: 10,
  image: null,
}

const SOURCE: TesterQuestionSource = {
  path: 'nba/single-answer.yaml',
  category: 'nba',
  entry: {
    type: 'single-answer',
    slug: 'kobe-81-point-game',
    description: 'Which team did Kobe score 81 against?',
    level: 5,
    tags: { era: '2000s' },
    options: [
      { text: 'Toronto Raptors', is_correct: true },
      { text: 'Dallas Mavericks' },
    ],
  },
}

vi.mock('./api', () => ({
  createTesterQuestion: vi.fn(),
  updateTesterQuestion: vi.fn(),
}))

async function openEditor(editing?: { question: TesterQuestionCard; source: TesterQuestionSource }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <QuestionEditor config={CONFIG} editing={editing} onClose={() => {}} />
      </ToastProvider>
    </QueryClientProvider>,
  )
  return await import('./api')
}

describe('the question editor', () => {
  it('seeds the form from the file, not from the row', async () => {
    await openEditor({ question: CARD, source: SOURCE })

    // The entry authored no clock, so the box is empty even though the row has
    // a 10 on it. A form filled in from the row would send that 10 back as this
    // question's own override and detach it from its file's tempo.
    expect(screen.getByLabelText('Seconds on the clock')).toHaveValue(null)
    expect(screen.getByLabelText('Question')).toHaveValue(String(SOURCE.entry.description))
    expect(screen.getByDisplayValue('Toronto Raptors')).toBeInTheDocument()
  })

  it('freezes the slug of a question that already exists', async () => {
    await openEditor({ question: CARD, source: SOURCE })

    // Changing it would not rename a question — it would retire one and author
    // another, which is a decision to make in the file.
    expect(screen.getByLabelText('Slug')).toBeDisabled()
  })

  it('leaves out the optional keys nobody filled in', async () => {
    const api = await openEditor({ question: CARD, source: SOURCE })

    await userEvent.click(screen.getByRole('button', { name: /save and sync/i }))

    const entry = vi.mocked(api.updateTesterQuestion).mock.calls[0][2]
    expect(entry).not.toHaveProperty('time_limit_seconds')
    expect(entry).not.toHaveProperty('image')
    expect(entry).not.toHaveProperty('pre_question_info')
    // …while everything the file did say survives the round trip.
    expect(entry.slug).toBe('kobe-81-point-game')
    expect(entry.tags).toEqual({ era: '2000s' })
    expect(entry.options).toHaveLength(2)
  })

  it('sends a clock only when one was actually typed', async () => {
    const api = await openEditor({ question: CARD, source: SOURCE })

    await userEvent.type(screen.getByLabelText('Seconds on the clock'), '25')
    await userEvent.click(screen.getByRole('button', { name: /save and sync/i }))

    expect(vi.mocked(api.updateTesterQuestion).mock.calls[0][2].time_limit_seconds).toBe(25)
  })

  it('creates against the category, which is not a field of the entry', async () => {
    const api = await openEditor()

    await userEvent.type(screen.getByLabelText('Slug'), 'a-new-one')
    await userEvent.type(screen.getByLabelText('Question'), 'Who won it?')
    await userEvent.click(screen.getByRole('button', { name: /create and sync/i }))

    const [category, entry] = vi.mocked(api.createTesterQuestion).mock.calls[0]
    // A resource file states its category once at the top, and the loader
    // refuses an entry that disagrees with the file it sits in.
    expect(category).toBe('nba')
    expect(entry).not.toHaveProperty('category')
    expect(entry.type).toBe('single-answer')
  })

  it('starts a new question at the smallest shape the loader accepts', async () => {
    await openEditor()

    // Two option rows, not one empty one: the first thing an author meets
    // should be the shape of a valid question, not a refusal counting how many
    // they are short.
    expect(screen.getAllByPlaceholderText('What the button says')).toHaveLength(2)
  })

  it('drops an option row that was added and never filled in', async () => {
    const api = await openEditor()

    await userEvent.type(screen.getByLabelText('Slug'), 'a-new-one')
    await userEvent.click(screen.getByRole('button', { name: /add option/i }))
    const boxes = screen.getAllByPlaceholderText('What the button says')
    await userEvent.type(boxes[0], 'Boston Celtics')
    await userEvent.type(boxes[1], 'Los Angeles Lakers')
    await userEvent.click(screen.getByRole('button', { name: /create and sync/i }))

    // Three rows on screen, two authored options in the file.
    expect(vi.mocked(api.createTesterQuestion).mock.calls[0][1].options).toHaveLength(2)
  })

  it('starts over when the answer shape changes', async () => {
    await openEditor()

    await userEvent.selectOptions(screen.getByLabelText('Answer shape'), 'ordering')

    // The old shape's keys mean nothing to the new one, and the loader rejects
    // unknown keys by name — so carrying them over would author a question that
    // cannot be saved.
    expect(screen.queryByPlaceholderText('What the button says')).not.toBeInTheDocument()
    expect(screen.getByLabelText('Instruction')).toBeInTheDocument()
  })
})

describe('the blank entries', () => {
  it('covers every answer shape the API publishes', () => {
    // The registry is `Record<QuestionType, …>`, so this is really a check that
    // the union and the backend's own list have not drifted apart — a shape the
    // API knows about and the editor does not is one nobody can author.
    for (const type of CONFIG.types) {
      expect(BLANK_ENTRIES[type.value]).toBeTypeOf('function')
      expect(BLANK_ENTRIES[type.value]()).toBeTypeOf('object')
    }
  })
})

describe('pruneEntry', () => {
  it('removes empty rows without touching anything else', () => {
    expect(
      pruneEntry({
        items: ['One', '  ', 'Two'],
        hints: ['A clue', ''],
        cells: [{ row: 'A', column: 'B', answers: ['Jordan'] }, { row: 'A', column: 'C', answers: [] }],
        instruction: 'Earliest first.',
      }),
    ).toEqual({
      items: ['One', 'Two'],
      hints: ['A clue'],
      cells: [{ row: 'A', column: 'B', answers: ['Jordan'] }],
      instruction: 'Earliest first.',
    })
  })

  it('does not try to make a short list long enough', () => {
    // Deliberately: how many a type needs is the loader's rule, and its refusal
    // names the type and the number. A form that padded the list would author
    // blank options to dodge a message that was about to be helpful.
    expect(pruneEntry({ items: ['', ''] })).toEqual({ items: [] })
  })
})

describe('describeRefusal', () => {
  it('shows every problem the loader found, not just the summary', () => {
    const error = new ApiError({
      code: 'validation_failed',
      message: 'Invalid question resources.',
      details: ['nba/ordering.yaml: items must be distinct', "'who-scored' is already stored"] as never,
    })

    expect(describeRefusal(error)).toContain('items must be distinct')
    expect(describeRefusal(error)).toContain('already stored')
  })

  it('falls back to the message when there is no list', () => {
    expect(
      describeRefusal(new ApiError({ code: 'validation_failed', message: 'A question needs a slug.' })),
    ).toBe('A question needs a slug.')
  })
})

describe('the catalog card’s verbs', () => {
  function renderCard(question: TesterQuestionCard, handlers: Record<string, () => void>) {
    return render(
      <MemoryRouter>
        <QuestionCatalogCard
          question={question}
          typeLabel="Single answer"
          onEdit={handlers.onEdit}
          onToggleActive={handlers.onToggleActive}
        />
      </MemoryRouter>,
    )
  }

  it('offers to retire a live question, never to delete it', async () => {
    const onToggleActive = vi.fn()
    renderCard(CARD, { onEdit: vi.fn(), onToggleActive })

    // A matchup that already played this question points at its row, so there
    // is no delete here and there must not be one.
    expect(screen.queryByRole('button', { name: /delete/i })).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Retire' }))
    expect(onToggleActive).toHaveBeenCalled()
  })

  it('offers to restore a retired one', () => {
    renderCard({ ...CARD, is_active: false }, { onEdit: vi.fn(), onToggleActive: vi.fn() })

    expect(screen.getByRole('button', { name: 'Restore' })).toBeInTheDocument()
  })

  it('keeps the verbs out of the link that opens the rehearsal', async () => {
    const onEdit = vi.fn()
    renderCard(CARD, { onEdit, onToggleActive: vi.fn() })

    // A <button> inside an <a> is invalid HTML and browsers disagree about
    // whether the click navigates too — which here would mean retiring a
    // question and being thrown into a rehearsal of it.
    expect(screen.getByRole('link')).not.toContainElement(
      screen.getByRole('button', { name: 'Edit' }),
    )
    await userEvent.click(screen.getByRole('button', { name: 'Edit' }))
    expect(onEdit).toHaveBeenCalled()
  })
})
