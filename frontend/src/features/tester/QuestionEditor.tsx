import { useState, type ReactNode } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { FileCode2, Plus, Trash2 } from 'lucide-react'
import { Button } from '../../components/Button'
import { Input } from '../../components/Input'
import { Modal } from '../../components/Modal'
import { useToast } from '../../hooks/useToast'
import type {
  QuestionType,
  TesterConfig,
  TesterQuestionCard,
  TesterQuestionSource,
  TesterWriteResult,
} from '../../lib/api/types'
import { createTesterQuestion, updateTesterQuestion } from './api'
import { BLANK_ENTRIES, describeRefusal, pruneEntry, type EditorProps } from './entryDrafts'
import {
  FreeTextFields,
  GradualHintsFields,
  ImageAnswerFields,
  LabelledInput,
  MatrixFields,
  MultipleAnswerFields,
  NameAsManyFields,
  OrderingFields,
  SingleAnswerFields,
  TrueFalseFields,
} from './EntryFields'

const ENTRY_EDITORS: Record<QuestionType, (props: EditorProps) => ReactNode> = {
  'single-answer': SingleAnswerFields,
  'image-answer': ImageAnswerFields,
  'multiple-answer': MultipleAnswerFields,
  'true-false': TrueFalseFields,
  'free-text': FreeTextFields,
  ordering: OrderingFields,
  matrix: MatrixFields,
  'gradual-hints': GradualHintsFields,
  'name-as-many': NameAsManyFields,
}

/*
 * The modal a question is written in.
 *
 * ## What saving actually does, and why the toast says so
 *
 * This form does not edit a database row. A save `POST`s or `PUT`s an *entry*
 * — the YAML mapping a question is authored as — and the backend splices it
 * into `backend/apps/questions/resources/<category>/<type>.yaml`, then runs the
 * ordinary `sync_questions` over that category. Two effects, and the second is
 * the one that puts the question in the database.
 *
 * So a question written here is a question written **to the repository**: it
 * shows up in `git diff`, it is reviewable as the text its author would have
 * typed, and it survives the next deploy's sync rather than being undone by it.
 * That is worth the toast naming the file, because it is the difference between
 * this page and an admin form, and it is the thing a maintainer needs to know
 * to go and commit what they just did.
 *
 * ## The form is forgiving; the loader is the authority
 *
 * Nothing here decides what a valid question is. Every rule — exactly one
 * correct option, no repeated ordering item, a clock that outlasts a hint
 * schedule — lives once in `apps.questions.schemas` and is enforced at load
 * time, and a refusal comes back as the message that file wrote. Mirroring any
 * of it here would be a second copy of the contract, drifting by *accepting*
 * what the loader refuses, which is the worse direction to drift in.
 *
 * What the form does instead is drop empty rows on the way out (`pruneEntry`)
 * and unset the optional keys nobody filled in — because in a resource file an
 * absent key is not an empty one. A missing `time_limit_seconds` is how an
 * entry takes the tempo its whole file sets; writing `""` or `0` would opt it
 * out of that silently.
 *
 * ## Slug and type are fixed once a question exists
 *
 * Both are editable on a create and read-only afterwards. The slug is the key
 * the loader upserts on, so changing it does not rename a question — it retires
 * one and creates another, which is a decision worth making deliberately in the
 * file rather than by clicking into a text box. The backend handles it if it is
 * ever asked to; this form does not ask.
 */

/** Everything above the type-specific section — shared by all nine shapes. */
interface Draft {
  category: string
  type: QuestionType
  slug: string
  description: string
  level: string
  /** Kept as rows rather than as an object so a half-typed key does not
   *  collapse two facets into one while it is being typed. */
  tags: { key: string; value: string }[]
  timeLimit: string
  preQuestionInfo: string
  image: string
  /** Every key the answer shape owns — options, cells, hints, and the rest. */
  entry: Record<string, unknown>
}

const FALLBACK_TYPE: QuestionType = 'single-answer'

function blankDraft(category: string, type: QuestionType): Draft {
  return {
    category,
    type,
    slug: '',
    description: '',
    level: '3',
    tags: [],
    timeLimit: '',
    preQuestionInfo: '',
    image: '',
    entry: BLANK_ENTRIES[type](),
  }
}

/** A stored entry, split back into the form's two halves.
 *
 *  The shared keys come off the top and everything left is the answer shape's
 *  own — which is what lets one form edit nine of them without knowing what the
 *  ninth contains. */
function draftFromSource(source: TesterQuestionSource): Draft {
  const { type, slug, description, level, tags, time_limit_seconds, pre_question_info, image, ...rest } =
    source.entry as Record<string, unknown>

  return {
    category: source.category,
    type: (type as QuestionType) ?? FALLBACK_TYPE,
    slug: String(slug ?? ''),
    description: String(description ?? ''),
    level: String(level ?? ''),
    tags: Object.entries((tags as Record<string, string>) ?? {}).map(([key, value]) => ({
      key,
      value: String(value),
    })),
    timeLimit: time_limit_seconds === undefined ? '' : String(time_limit_seconds),
    // An authored empty string is not the same as an absent key — it is how one
    // entry opts *out* of a task screen its file sets for everything else — so
    // the distinction is carried through the form rather than flattened here.
    preQuestionInfo: pre_question_info === undefined ? '' : String(pre_question_info),
    image: image === undefined || image === null ? '' : String(image),
    // `rest` keeps whatever the file had, including keys this editor has no
    // control for. An entry is only ever read, edited and written whole, so a
    // field added to the schemas before it is added to this form survives a
    // save here instead of being silently dropped.
    entry: rest,
  }
}

/** The draft as the mapping the backend takes. */
function entryFromDraft(draft: Draft, { explicitPreQuestionInfo }: { explicitPreQuestionInfo: boolean }) {
  const tags = Object.fromEntries(
    draft.tags.filter((tag) => tag.key.trim()).map((tag) => [tag.key.trim(), tag.value.trim()]),
  )

  const entry: Record<string, unknown> = {
    ...pruneEntry(draft.entry),
    type: draft.type,
    slug: draft.slug.trim(),
    description: draft.description.trim(),
    level: Number(draft.level),
  }
  if (Object.keys(tags).length > 0) entry.tags = tags
  // Each of these is *absent* rather than empty when unset, because absent is
  // what means "take the file's" — see the module note above.
  if (draft.timeLimit.trim()) entry.time_limit_seconds = Number(draft.timeLimit)
  if (draft.preQuestionInfo.trim() || explicitPreQuestionInfo) {
    entry.pre_question_info = draft.preQuestionInfo
  }
  if (draft.image.trim()) entry.image = draft.image.trim()
  return entry
}

export function QuestionEditor({
  onClose,
  config,
  /** The question being edited, with the file entry behind it. Absent is a
   *  create — the two modes differ only in which fields are frozen and which
   *  request is sent, so they are one component rather than two that would
   *  drift apart a field at a time. */
  editing,
}: {
  onClose: () => void
  config: TesterConfig | null | undefined
  editing?: { question: TesterQuestionCard; source: TesterQuestionSource }
}) {
  const toast = useToast()
  const queryClient = useQueryClient()
  const isEdit = editing !== undefined

  /* Seeded once, on mount. The caller renders this component only while the
   * modal is up (`{editing && <QuestionEditor …/>}`), so "open" and "mounted"
   * are the same event and there is nothing to re-seed on — which is the point:
   * an effect that re-seeded from a prop would wipe a half-typed question the
   * moment a background refetch handed back a new `config` object. */
  const [draft, setDraft] = useState<Draft>(() =>
    editing
      ? draftFromSource(editing.source)
      : blankDraft(config?.categories[0]?.slug ?? '', FALLBACK_TYPE),
  )
  /* Whether the entry *had* a `pre_question_info` key, so that clearing the box
   * on an entry that authored `""` keeps writing `""` rather than dropping to
   * "whatever the file says" — which are opposite meanings for the one type
   * whose file sets an instruction. */
  const [explicitPreQuestionInfo, setExplicitPreQuestionInfo] = useState(
    editing !== undefined && 'pre_question_info' in editing.source.entry,
  )

  const save = useMutation({
    mutationFn: (entry: Record<string, unknown>): Promise<TesterWriteResult> =>
      editing
        ? updateTesterQuestion(editing.question.type, editing.question.id, entry)
        : createTesterQuestion(draft.category, entry),
    onSuccess: (result) => {
      // Both halves, because both happened and they can disagree — a save that
      // wrote the file and loaded nothing is the failure mode nobody would
      // notice from a tick.
      toast.success(
        result.action === 'created' ? 'Question written' : 'Question updated',
        {
          description: `${result.source.path} · ${result.sync.summary}`,
          duration: 6000,
        },
      )
      void queryClient.invalidateQueries({ queryKey: ['tester'] })
      onClose()
    },
    onError: (error) => {
      toast.error('The catalog refused that', {
        description: describeRefusal(error),
        duration: 0,
      })
    },
  })

  const TypeFields = ENTRY_EDITORS[draft.type]

  return (
    <Modal
      open
      onClose={onClose}
      widthClass="max-w-2xl"
      title={isEdit ? 'Edit question' : 'New question'}
      description={
        isEdit
          ? 'Saving rewrites this question’s block in its resource file, then reloads the catalog from it.'
          : 'Saving appends a block to the category’s resource file for this answer shape, then loads it.'
      }
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={save.isPending}>
            Cancel
          </Button>
          <Button
            onClick={() => save.mutate(entryFromDraft(draft, { explicitPreQuestionInfo }))}
            disabled={save.isPending || !draft.category}
          >
            <FileCode2 size={15} aria-hidden />
            {save.isPending ? 'Saving…' : isEdit ? 'Save and sync' : 'Create and sync'}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        {/* --- What and where ------------------------------------------- */}
        <div className="grid gap-3 sm:grid-cols-2">
          <FormSelect
            label="Category"
            value={draft.category}
            disabled={isEdit}
            hint={isEdit ? 'A question does not move sport.' : undefined}
            onChange={(category) => setDraft((current) => ({ ...current, category }))}
            options={(config?.categories ?? []).map((entry) => ({
              value: entry.slug,
              label: entry.name,
            }))}
          />
          <FormSelect
            label="Answer shape"
            value={draft.type}
            disabled={isEdit}
            hint={
              isEdit
                ? 'Retyping a question is a new slug — the file it lives in is the file for its shape.'
                : 'Decides which resource file the block goes in.'
            }
            onChange={(value) =>
              setDraft((current) => ({
                ...current,
                type: value as QuestionType,
                // The old shape's keys mean nothing to the new one, and the
                // loader rejects unknown keys by name — so switching starts
                // that shape's own minimum rather than carrying wreckage over.
                entry: BLANK_ENTRIES[value as QuestionType](),
              }))
            }
            options={(config?.types ?? []).map((entry) => ({
              value: entry.value,
              label: entry.label,
            }))}
          />
        </div>

        <LabelledInput
          label="Slug"
          className="font-mono text-xs"
          placeholder="nba-most-championships-franchise"
          value={draft.slug}
          disabled={isEdit}
          onChange={(slug) => setDraft((current) => ({ ...current, slug }))}
          hint={
            isEdit
              ? 'The key the loader upserts on — frozen here. Changing it would retire this question and author another, which is a decision to make in the file.'
              : 'Lowercase and hyphenated, unique across every category and every answer shape.'
          }
        />

        <label className="flex flex-col gap-1.5">
          <span className="text-sm font-medium text-ash">Question</span>
          <textarea
            aria-label="Question"
            rows={3}
            value={draft.description}
            placeholder="Which franchise has won the most NBA championships?"
            onChange={(event) =>
              setDraft((current) => ({ ...current, description: event.target.value }))
            }
            className="w-full rounded-input border border-chalk/8 bg-raised p-3 text-sm leading-relaxed text-chalk outline-none transition-all duration-150 placeholder:text-ash/50 focus:border-volt focus:ring-2 focus:ring-volt/25"
          />
          <span className="text-xs text-ash/70">Exactly as the player reads it.</span>
        </label>

        <div className="grid gap-3 sm:grid-cols-2">
          <LabelledInput
            label="Difficulty"
            type="number"
            value={draft.level}
            onChange={(level) => setDraft((current) => ({ ...current, level }))}
            hint="1 — a casual fan gets it. 10 — a statistician might."
          />
          <LabelledInput
            label="Seconds on the clock"
            type="number"
            value={draft.timeLimit}
            onChange={(timeLimit) => setDraft((current) => ({ ...current, timeLimit }))}
            hint="Leave empty to take the tempo its resource file sets for every question of this shape — which is the ordinary case."
          />
        </div>

        <TagRows tags={draft.tags} onChange={(tags) => setDraft((current) => ({ ...current, tags }))} />

        {/* --- The answer shape's own fields ---------------------------- */}
        <div className="flex flex-col gap-4 rounded-tile border border-chalk/8 bg-raised/40 p-3.5">
          <TypeFields
            entry={draft.entry}
            patch={(change) =>
              setDraft((current) => {
                const entry = { ...current.entry, ...change }
                // An explicit `undefined` is how an editor *removes* a key —
                // a matrix switching to a derived grid must author no cells at
                // all, and a key set to undefined would be sent as null.
                for (const [key, value] of Object.entries(change)) {
                  if (value === undefined) delete entry[key]
                }
                return { ...current, entry }
              })
            }
          />
        </div>

        {/* --- The rarely-set rest -------------------------------------- */}
        <details className="rounded-tile border border-chalk/8 p-3">
          <summary className="cursor-pointer text-sm font-medium text-ash">
            Illustration and task screen
          </summary>
          <div className="mt-3 flex flex-col gap-3">
            <LabelledInput
              label="Image"
              className="font-mono text-xs"
              placeholder="court-free-throw-line.png"
              value={draft.image}
              onChange={(image) => setDraft((current) => ({ ...current, image }))}
              hint="A file already in this category's images/ folder — a picture of what is being asked about, not the answer options."
            />
            <LabelledInput
              label="Pre-question info"
              placeholder="Click to order them from earliest to latest"
              value={draft.preQuestionInfo}
              onChange={(preQuestionInfo) => {
                setExplicitPreQuestionInfo(true)
                setDraft((current) => ({ ...current, preQuestionInfo }))
              }}
              hint="Shown alone on screen before the question, saying what the task is. Almost always set once for the whole file instead — leave it empty unless this one question is unusual."
            />
          </div>
        </details>
      </div>
    </Modal>
  )
}

/** Free-form facets, as rows. Keys are the author's own — the filter that reads
 *  them is `tags__era="2000s"`, so what matters is being consistent within a
 *  category, which nothing here can enforce and a dropdown would pretend to. */
function TagRows({
  tags,
  onChange,
}: {
  tags: { key: string; value: string }[]
  onChange: (tags: { key: string; value: string }[]) => void
}) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-end justify-between gap-3">
        <div>
          <span className="text-sm font-medium text-ash">Tags</span>
          <p className="text-xs text-ash/70">
            Facets themed rooms filter on — topic, era. Keys are yours; keep them consistent
            within a category or a room finds nothing.
          </p>
        </div>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          onClick={() => onChange([...tags, { key: '', value: '' }])}
        >
          <Plus size={14} aria-hidden />
          Add tag
        </Button>
      </div>
      {tags.map((tag, index) => (
        <div key={index} className="flex items-center gap-2">
          <Input
            size="sm"
            value={tag.key}
            placeholder="topic"
            aria-label={`Tag ${index + 1} key`}
            onChange={(event) =>
              onChange(tags.map((each, at) => (at === index ? { ...each, key: event.target.value } : each)))
            }
          />
          <Input
            size="sm"
            value={tag.value}
            placeholder="teams"
            aria-label={`Tag ${index + 1} value`}
            onChange={(event) =>
              onChange(
                tags.map((each, at) => (at === index ? { ...each, value: event.target.value } : each)),
              )
            }
          />
          <button
            type="button"
            aria-label={`Remove tag ${index + 1}`}
            onClick={() => onChange(tags.filter((_, at) => at !== index))}
            className="shrink-0 rounded-tile p-2 text-ash transition-colors hover:bg-wrong/10 hover:text-wrong"
          >
            <Trash2 size={15} aria-hidden />
          </button>
        </div>
      ))}
    </div>
  )
}

function FormSelect({
  label,
  value,
  options,
  onChange,
  disabled,
  hint,
}: {
  label: string
  value: string
  options: { value: string; label: string }[]
  onChange: (value: string) => void
  disabled?: boolean
  hint?: string
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-sm font-medium text-ash">{label}</span>
      {/* Named explicitly — see `LabelledInput`; the hint below is part of this
          label's text content and must not be part of its name. */}
      <select
        aria-label={label}
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        className="h-11 w-full rounded-input border border-chalk/8 bg-raised px-3 text-sm text-chalk outline-none transition-all duration-150 focus:border-volt focus:ring-2 focus:ring-volt/25 disabled:opacity-60"
      >
        {options.map((option) => (
          <option key={option.value} value={option.value} className="bg-raised">
            {option.label}
          </option>
        ))}
      </select>
      {hint && <span className="text-xs leading-relaxed text-ash/70">{hint}</span>}
    </label>
  )
}
