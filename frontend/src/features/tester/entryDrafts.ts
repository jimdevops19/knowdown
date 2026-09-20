import type { QuestionType } from '../../lib/api/types'
import { ApiError } from '../../lib/api/errors'

/*
 * The question editor's non-visual half: what a blank entry of each shape is,
 * what to drop from one on the way out, and how to read a refusal.
 *
 * Apart from `EntryFields.tsx` for the reason `components/toastContext.ts` is
 * apart from `Toast.tsx` — a module that exports both components and plain
 * values breaks React Fast Refresh, so the values live in a `.ts` of their own
 * and the `.tsx` next door exports nothing but components.
 */

/** Every key a question of this type may carry, beyond the shared ones.
 *
 *  What every per-type editor in `EntryFields.tsx` is handed. `patch` merges
 *  keys into the draft; passing `undefined` *removes* one, which is how an
 *  optional key is unset — and not the same as setting it empty, because in a
 *  resource file an absent key and an empty one mean different things. */
export interface EditorProps {
  entry: Record<string, unknown>
  patch: (change: Record<string, unknown>) => void
}

/** What a brand-new question of each shape starts as.
 *
 *  Pre-filled with the *minimum the loader accepts* — two options, three
 *  ordering items — rather than with one empty row, so the first thing an
 *  author meets is the shape of a valid question rather than a refusal
 *  counting how many they are short. */
export const BLANK_ENTRIES: Record<QuestionType, () => Record<string, unknown>> = {
  'single-answer': () => ({
    options: [
      { text: '', is_correct: true },
      { text: '', is_correct: false },
    ],
  }),
  'image-answer': () => ({
    options: [
      { image: '', label: '', is_correct: true },
      { image: '', label: '', is_correct: false },
    ],
  }),
  'multiple-answer': () => ({
    options: [
      { text: '', is_correct: true },
      { text: '', is_correct: true },
      { text: '', is_correct: false },
    ],
  }),
  'true-false': () => ({ answer: true }),
  'free-text': () => ({ accepted_answers: [''] }),
  ordering: () => ({ instruction: '', items: ['', '', ''] }),
  matrix: () => ({ kind: 'authored', rows: ['', ''], columns: ['', ''], cells: [] }),
  'gradual-hints': () => ({
    hints: ['', ''],
    answer_fields: [{ label: '', kind: 'text', accepted_answers: [''] }],
  }),
  'name-as-many': () => ({
    dataset: 'nba-career-stats',
    stat: '',
    comparison: 'gte',
    threshold: 1000,
    target_score: 20,
  }),
}


/**
 * Drop the rows an author started and never filled in.
 *
 * A blank option at the bottom of a list is the shape of somebody clicking
 * "add" once too often, not an authored option — and it is the single most
 * common way a save would be refused for a reason that is not about the
 * question. Pruning here rather than validating means the form does the
 * forgiving thing and the loader stays the authority on everything else.
 *
 * It is deliberately shallow-minded: it removes *empty* things and changes
 * nothing else. A list that ends up too short is still refused by the loader,
 * with its own message about how many that type needs.
 */
export function pruneEntry(entry: Record<string, unknown>): Record<string, unknown> {
  const pruned: Record<string, unknown> = { ...entry }

  if (Array.isArray(pruned.options)) {
    pruned.options = (pruned.options as Record<string, unknown>[]).filter(
      (option) => String(option.text ?? option.image ?? '').trim() !== '',
    )
  }
  for (const key of ['items', 'hints', 'accepted_answers', 'rows', 'columns']) {
    if (Array.isArray(pruned[key])) {
      pruned[key] = (pruned[key] as string[]).map((value) => value.trim()).filter(Boolean)
    }
  }
  if (Array.isArray(pruned.answer_fields)) {
    pruned.answer_fields = (pruned.answer_fields as Record<string, unknown>[])
      .filter((field) => String(field.label ?? '').trim() !== '')
      .map((field) => ({
        ...field,
        accepted_answers: ((field.accepted_answers as string[]) ?? [])
          .map((value) => value.trim())
          .filter(Boolean),
      }))
  }
  if (Array.isArray(pruned.cells)) {
    pruned.cells = (pruned.cells as Record<string, unknown>[]).filter(
      (cell) => Array.isArray(cell.answers) && (cell.answers as unknown[]).length > 0,
    )
  }
  return pruned
}

/**
 * A refusal, in the loader's own words.
 *
 * The backend collects *every* problem across the files it parsed rather than
 * raising at the first (`apps.core_common.exceptions.ValidationFailed`'s
 * `details`), specifically so somebody fixing a batch sees the whole list in
 * one run. That list is the most useful thing on the screen when a save fails,
 * so it is shown rather than flattened to the summary line above it.
 */
export function describeRefusal(error: unknown): string {
  if (!(error instanceof ApiError)) return 'Something went wrong. Please try again.'
  // `details` is typed as a mapping because that is what a serializer refusal
  // sends; a *resource* refusal sends the loader's flat list of problems, which
  // is the shape that matters here.
  const details: unknown = error.details
  const problems = Array.isArray(details) ? details : undefined
  if (problems && problems.length > 0) return problems.map(String).join(' · ')
  return error.message
}
