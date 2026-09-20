import { Plus, Trash2 } from 'lucide-react'
import type { ReactNode } from 'react'
import { Button } from '../../components/Button'
import { Input } from '../../components/Input'
import type { EditorProps } from './entryDrafts'

/*
 * The half of the question editor that differs per answer shape.
 *
 * ## Why this is a registry and not a switch
 *
 * `ENTRY_EDITORS` is keyed by `QuestionType`, exactly like `QUESTION_BOARDS` in
 * `features/play/QuestionBoard.tsx` and the four backend registries it mirrors
 * (`backend/CLAUDE.md`). The type is `Record<QuestionType, …>`, so adding a
 * question type to the union without adding an editor here is a **compile
 * error** rather than a form that renders a slug field and nothing else. That
 * is the whole reason for the shape: a new answer shape gets authored the week
 * it ships, and the failure mode of forgetting is a question type nobody can
 * create from this page and no error saying so.
 *
 * `BLANK_ENTRIES` is the same rule for the other direction — what a brand-new
 * question of each shape starts out as.
 *
 * ## What these editors are *not* responsible for
 *
 * Validity. Not one of these prevents a bad entry: two correct options on a
 * single-answer, a repeated ordering item, a `number` field keyed to words.
 * Every one of those rules is written down once, in `apps.questions.schemas`,
 * enforced at load time, and reported back by the save — and re-implementing
 * any of it here would be a second copy of the contract that drifts by
 * *accepting* what the loader refuses. The editors' job is to make the right
 * shape easy to type; the loader's job is to be the authority on it.
 *
 * The one thing they do suppress is the empty row. A blank option left at the
 * bottom of a list is a typo, not an authored option, so `prune` drops it on
 * the way out rather than making the author delete a row they never filled in.
 */

/* --- Small primitives the editors are built from --------------------------- */

/** A titled group inside the form, with an "add" verb on its right. */
function Section({
  title,
  hint,
  onAdd,
  addLabel,
  children,
}: {
  title: string
  hint?: string
  onAdd?: () => void
  addLabel?: string
  children: ReactNode
}) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-end justify-between gap-3">
        <div>
          <span className="text-sm font-medium text-ash">{title}</span>
          {hint && <p className="text-xs text-ash/70">{hint}</p>}
        </div>
        {onAdd && (
          <Button type="button" size="sm" variant="ghost" onClick={onAdd}>
            <Plus size={14} aria-hidden />
            {addLabel ?? 'Add'}
          </Button>
        )}
      </div>
      {children}
    </div>
  )
}

/** The delete button every repeated row carries, sized to sit beside an input. */
function RemoveButton({ onClick, label }: { onClick: () => void; label: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      className="shrink-0 rounded-tile p-2 text-ash transition-colors hover:bg-wrong/10 hover:text-wrong"
    >
      <Trash2 size={15} aria-hidden />
    </button>
  )
}

/** A list of plain strings — ordering items, hints, accepted spellings.
 *
 *  Order is meaningful in two of the three (an ordering question's list order
 *  *is* its answer; a hint list is the reveal schedule), so rows are never
 *  sorted and adding appends. The backend numbers positions from this order,
 *  which is why no position is editable here: there is nothing to keep in step. */
export function StringList({
  title,
  hint,
  values,
  onChange,
  placeholder,
  addLabel,
}: {
  title: string
  hint?: string
  values: string[]
  onChange: (values: string[]) => void
  placeholder?: string
  addLabel?: string
}) {
  return (
    <Section title={title} hint={hint} addLabel={addLabel} onAdd={() => onChange([...values, ''])}>
      <div className="flex flex-col gap-2">
        {values.map((value, index) => (
          <div key={index} className="flex items-center gap-2">
            <span className="nums w-5 shrink-0 text-right text-xs text-ash/60">{index + 1}</span>
            <Input
              size="sm"
              value={value}
              placeholder={placeholder}
              onChange={(event) =>
                onChange(values.map((each, at) => (at === index ? event.target.value : each)))
              }
            />
            <RemoveButton
              label={`Remove ${title} ${index + 1}`}
              onClick={() => onChange(values.filter((_, at) => at !== index))}
            />
          </div>
        ))}
      </div>
    </Section>
  )
}

/** One text option and whether it is right. `mode` is the only difference
 *  between the two types that use it: a single-answer's correct option is a
 *  radio (picking one un-picks the last), a multiple-answer's is a checkbox. */
function TextOptions({
  entry,
  patch,
  mode,
  hint,
}: EditorProps & { mode: 'one' | 'many'; hint: string }) {
  const options = (entry.options as { text?: string; is_correct?: boolean }[]) ?? []
  const set = (next: typeof options) => patch({ options: next })

  return (
    <Section
      title="Options"
      hint={hint}
      addLabel="Add option"
      onAdd={() => set([...options, { text: '', is_correct: false }])}
    >
      <div className="flex flex-col gap-2">
        {options.map((option, index) => (
          <div key={index} className="flex items-center gap-2">
            <input
              type={mode === 'one' ? 'radio' : 'checkbox'}
              name="correct-option"
              checked={Boolean(option.is_correct)}
              aria-label={`Option ${index + 1} is correct`}
              onChange={(event) =>
                set(
                  options.map((each, at) => ({
                    ...each,
                    // A radio un-picks its siblings; a checkbox leaves them be.
                    is_correct:
                      at === index
                        ? event.target.checked
                        : mode === 'one'
                          ? false
                          : Boolean(each.is_correct),
                  })),
                )
              }
              className="h-4 w-4 shrink-0 accent-court"
            />
            <Input
              size="sm"
              value={option.text ?? ''}
              placeholder="What the button says"
              onChange={(event) =>
                set(options.map((each, at) => (at === index ? { ...each, text: event.target.value } : each)))
              }
            />
            <RemoveButton
              label={`Remove option ${index + 1}`}
              onClick={() => set(options.filter((_, at) => at !== index))}
            />
          </div>
        ))}
      </div>
    </Section>
  )
}

/* --- One editor per answer shape ------------------------------------------- */

export function SingleAnswerFields(props: EditorProps) {
  return <TextOptions {...props} mode="one" hint="Two or more, exactly one of them right." />
}

export function MultipleAnswerFields(props: EditorProps) {
  return (
    <TextOptions
      {...props}
      mode="many"
      hint="Three or more. At least two right, and at least one wrong — a 'select all' where everything counts has one answer."
    />
  )
}

export function ImageAnswerFields({ entry, patch }: EditorProps) {
  const options = (entry.options as { image?: string; label?: string; is_correct?: boolean }[]) ?? []
  const set = (next: typeof options) => patch({ options: next })

  return (
    <Section
      title="Image options"
      hint="Filenames inside the category's images/ folder — not paths, and the file has to already be there."
      addLabel="Add image"
      onAdd={() => set([...options, { image: '', label: '', is_correct: false }])}
    >
      <div className="flex flex-col gap-2">
        {options.map((option, index) => (
          <div key={index} className="flex items-center gap-2">
            <input
              type="radio"
              name="correct-image"
              checked={Boolean(option.is_correct)}
              aria-label={`Image ${index + 1} is correct`}
              onChange={() =>
                set(options.map((each, at) => ({ ...each, is_correct: at === index })))
              }
              className="h-4 w-4 shrink-0 accent-court"
            />
            <Input
              size="sm"
              className="font-mono text-xs"
              value={option.image ?? ''}
              placeholder="court-free-throw-line.png"
              onChange={(event) =>
                set(options.map((each, at) => (at === index ? { ...each, image: event.target.value } : each)))
              }
            />
            <Input
              size="sm"
              value={option.label ?? ''}
              placeholder="Caption (optional)"
              onChange={(event) =>
                set(options.map((each, at) => (at === index ? { ...each, label: event.target.value } : each)))
              }
            />
            <RemoveButton
              label={`Remove image ${index + 1}`}
              onClick={() => set(options.filter((_, at) => at !== index))}
            />
          </div>
        ))}
      </div>
    </Section>
  )
}

export function TrueFalseFields({ entry, patch }: EditorProps) {
  return (
    <Section title="Answer" hint="What the statement in the description actually is.">
      <div className="flex gap-2">
        {[true, false].map((value) => (
          <button
            key={String(value)}
            type="button"
            onClick={() => patch({ answer: value })}
            className={`h-11 flex-1 rounded-input border text-sm font-medium transition-colors ${
              entry.answer === value
                ? 'border-volt bg-volt/12 text-chalk'
                : 'border-chalk/8 bg-raised text-ash hover:text-chalk'
            }`}
          >
            {value ? 'True' : 'False'}
          </button>
        ))}
      </div>
    </Section>
  )
}

export function FreeTextFields({ entry, patch }: EditorProps) {
  return (
    <StringList
      title="Accepted answers"
      hint="Every spelling that counts. Compared case-insensitively, so write the variants a person racing a clock would actually type."
      addLabel="Add spelling"
      placeholder="Kareem Abdul-Jabbar"
      values={(entry.accepted_answers as string[]) ?? []}
      onChange={(accepted_answers) => patch({ accepted_answers })}
    />
  )
}

export function OrderingFields({ entry, patch }: EditorProps) {
  return (
    <>
      <LabelledInput
        label="Instruction"
        hint="The rule for answering, shown apart from the question — 'Order them from most points to fewest'."
        value={(entry.instruction as string) ?? ''}
        onChange={(instruction) => patch({ instruction })}
      />
      <StringList
        title="Items, in their correct order"
        hint="Three or four. The list order is the answer — positions are never authored — and the board is shuffled before a player sees it."
        addLabel="Add item"
        values={(entry.items as string[]) ?? []}
        onChange={(items) => patch({ items })}
      />
    </>
  )
}

export function GradualHintsFields({ entry, patch }: EditorProps) {
  const fields =
    (entry.answer_fields as { label?: string; kind?: string; accepted_answers?: string[] }[]) ?? []
  const setFields = (next: typeof fields) => patch({ answer_fields: next })

  return (
    <>
      <StringList
        title="Hints, hardest first"
        hint="The list order is the reveal schedule: the first lands when the clock starts, each of the others one interval later."
        addLabel="Add hint"
        values={(entry.hints as string[]) ?? []}
        onChange={(hints) => patch({ hints })}
      />
      <LabelledInput
        label="Seconds between hints"
        hint="The clock has to outlast the schedule — the loader refuses a question whose last clue lands with no time left to use it."
        type="number"
        value={String(entry.hint_interval_seconds ?? '')}
        onChange={(value) =>
          patch({ hint_interval_seconds: value === '' ? undefined : Number(value) })
        }
      />

      <Section
        title="Answer fields"
        hint="The boxes the player fills in. Each is graded on its own, and carries every spelling that fills it."
        addLabel="Add field"
        onAdd={() => setFields([...fields, { label: '', kind: 'text', accepted_answers: [''] }])}
      >
        <div className="flex flex-col gap-3">
          {fields.map((field, index) => (
            <div key={index} className="flex flex-col gap-2 rounded-tile border border-chalk/8 p-3">
              <div className="flex items-center gap-2">
                <Input
                  size="sm"
                  value={field.label ?? ''}
                  placeholder="Year"
                  onChange={(event) =>
                    setFields(
                      fields.map((each, at) =>
                        at === index ? { ...each, label: event.target.value } : each,
                      ),
                    )
                  }
                />
                <select
                  aria-label={`Field ${index + 1} kind`}
                  value={field.kind ?? 'text'}
                  onChange={(event) =>
                    setFields(
                      fields.map((each, at) =>
                        at === index ? { ...each, kind: event.target.value } : each,
                      ),
                    )
                  }
                  className="h-11 shrink-0 rounded-input border border-chalk/8 bg-raised px-3 text-sm text-chalk outline-none focus:border-volt"
                >
                  <option value="text">Text</option>
                  <option value="number">Number</option>
                </select>
                <RemoveButton
                  label={`Remove field ${index + 1}`}
                  onClick={() => setFields(fields.filter((_, at) => at !== index))}
                />
              </div>
              <StringList
                title="Accepted answers"
                addLabel="Add spelling"
                values={field.accepted_answers ?? []}
                onChange={(accepted_answers) =>
                  setFields(
                    fields.map((each, at) => (at === index ? { ...each, accepted_answers } : each)),
                  )
                }
              />
            </div>
          ))}
        </div>
      </Section>
    </>
  )
}

export function MatrixFields({ entry, patch }: EditorProps) {
  const kind = (entry.kind as string) ?? 'authored'
  const rows = (entry.rows as string[]) ?? []
  const columns = (entry.columns as string[]) ?? []
  const cells =
    (entry.cells as { row?: string; column?: string; answers?: unknown[] }[]) ?? []

  return (
    <>
      <Section
        title="Where the answers come from"
        hint="A teams grid derives every cell from the roster artifact — both axes name franchises, and it authors no cells at all."
      >
        <div className="flex gap-2">
          {[
            { value: 'authored', label: 'Authored cells' },
            { value: 'teams', label: 'NBA franchises' },
          ].map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() =>
                patch({
                  kind: option.value,
                  // A teams grid may not author cells and an authored one must:
                  // the loader refuses either mistake by name, so switching
                  // here takes the other half with it rather than leaving a
                  // form that cannot be saved.
                  cells: option.value === 'teams' ? undefined : cells,
                })
              }
              className={`h-11 flex-1 rounded-input border text-sm font-medium transition-colors ${
                kind === option.value
                  ? 'border-volt bg-volt/12 text-chalk'
                  : 'border-chalk/8 bg-raised text-ash hover:text-chalk'
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>
      </Section>

      <StringList
        title="Rows"
        addLabel="Add row"
        values={rows}
        onChange={(next) => patch({ rows: next })}
      />
      <StringList
        title="Columns"
        addLabel="Add column"
        values={columns}
        onChange={(next) => patch({ columns: next })}
      />

      {kind === 'authored' && (
        <Section
          title="Cells"
          hint="One per intersection worth asking about — a grid is several sparse claims, not one, and credit is per authored cell. Answers are comma-separated; any one of them takes the square."
          addLabel="Add cell"
          onAdd={() =>
            patch({
              cells: [...cells, { row: rows[0] ?? '', column: columns[0] ?? '', answers: [] }],
            })
          }
        >
          <div className="flex flex-col gap-2">
            {cells.map((cell, index) => (
              <div key={index} className="flex items-center gap-2">
                <HeadingSelect
                  label={`Cell ${index + 1} row`}
                  value={cell.row ?? ''}
                  options={rows}
                  onChange={(row) =>
                    patch({ cells: cells.map((each, at) => (at === index ? { ...each, row } : each)) })
                  }
                />
                <HeadingSelect
                  label={`Cell ${index + 1} column`}
                  value={cell.column ?? ''}
                  options={columns}
                  onChange={(column) =>
                    patch({
                      cells: cells.map((each, at) => (at === index ? { ...each, column } : each)),
                    })
                  }
                />
                <Input
                  size="sm"
                  value={answersToText(cell.answers)}
                  placeholder="Michael Jordan, Ron Harper"
                  onChange={(event) =>
                    patch({
                      cells: cells.map((each, at) =>
                        at === index ? { ...each, answers: textToAnswers(event.target.value) } : each,
                      ),
                    })
                  }
                />
                <RemoveButton
                  label={`Remove cell ${index + 1}`}
                  onClick={() => patch({ cells: cells.filter((_, at) => at !== index) })}
                />
              </div>
            ))}
          </div>
        </Section>
      )}
    </>
  )
}

/*
 * A cell's answers, as one comma-separated line.
 *
 * The authored form is a list, and each entry may carry a `probability_score`
 * — how obvious the pick is, 2 to 10. Nothing on this platform *reads* that
 * number yet (see `backend/CLAUDE.md`), so a row of graders per name would be
 * a column of inputs for a value with no consumer, on the one editor that is
 * already the most crowded. So the common case is typed as a line, and the
 * long form is preserved: a cell whose answers were authored with grades keeps
 * them, because `textToAnswers` is only reached when the line is edited.
 *
 * The bare-string shorthand is the loader's own (`MatrixAnswerSpec` accepts a
 * string as `{answer: …}` at the default grade), so what this writes is what a
 * person writing the common case by hand would write.
 */
function answersToText(answers: unknown): string {
  if (!Array.isArray(answers)) return ''
  return answers
    .map((answer) =>
      typeof answer === 'string' ? answer : String((answer as { answer?: string }).answer ?? ''),
    )
    .join(', ')
}

function textToAnswers(text: string): string[] {
  return text
    .split(',')
    .map((value) => value.trim())
    .filter(Boolean)
}

function HeadingSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string
  value: string
  options: string[]
  onChange: (value: string) => void
}) {
  return (
    <select
      aria-label={label}
      value={value}
      onChange={(event) => onChange(event.target.value)}
      className="h-11 min-w-0 flex-1 rounded-input border border-chalk/8 bg-raised px-2 text-xs text-chalk outline-none focus:border-volt"
    >
      {/* The headings, plus whatever this cell currently names even if it is
          not one of them — a cell pointing at a row somebody just renamed must
          stay visible, or the form silently rewrites it on save. */}
      {[...new Set([value, ...options])].filter(Boolean).map((option) => (
        <option key={option} value={option} className="bg-raised">
          {option}
        </option>
      ))}
    </select>
  )
}

export function NameAsManyFields({ entry, patch }: EditorProps) {
  return (
    <>
      <p className="rounded-tile border border-chalk/8 bg-raised/60 p-3 text-xs leading-relaxed text-ash">
        This type has no options and no answer rows. What it stores is a line
        through a column of the baked career-stats artifact, and who qualifies
        is read at scoring time — so a stat the artifact does not carry, or a
        threshold nobody has ever cleared, is refused when you save.
      </p>
      <LabelledInput
        label="Dataset"
        hint="The baked artifact to read. Today there is one: nba-career-stats."
        value={(entry.dataset as string) ?? ''}
        onChange={(dataset) => patch({ dataset })}
      />
      <LabelledInput
        label="Stat"
        hint="A column of that artifact — three_pointers_made, points, rebounds…"
        value={(entry.stat as string) ?? ''}
        onChange={(stat) => patch({ stat })}
      />
      <Section title="Comparison" hint="Which side of the threshold qualifies.">
        <div className="flex gap-2">
          {[
            { value: 'gte', label: 'At least' },
            { value: 'lte', label: 'At most' },
          ].map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => patch({ comparison: option.value })}
              className={`h-11 flex-1 rounded-input border text-sm font-medium transition-colors ${
                entry.comparison === option.value
                  ? 'border-volt bg-volt/12 text-chalk'
                  : 'border-chalk/8 bg-raised text-ash hover:text-chalk'
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>
      </Section>
      <LabelledInput
        label="Threshold"
        type="number"
        value={String(entry.threshold ?? '')}
        onChange={(value) => patch({ threshold: value === '' ? undefined : Number(value) })}
      />
      <LabelledInput
        label="Target score"
        hint="The pile of fame points that counts as full credit. It cannot exceed what is actually on the board."
        type="number"
        value={String(entry.target_score ?? '')}
        onChange={(value) => patch({ target_score: value === '' ? undefined : Number(value) })}
      />
    </>
  )
}

/** A labelled single input — the shape most of the scalar fields above take. */
export function LabelledInput({
  label,
  hint,
  value,
  onChange,
  type,
  placeholder,
  className,
  disabled,
}: {
  label: string
  hint?: string
  value: string
  onChange: (value: string) => void
  type?: string
  placeholder?: string
  className?: string
  /** For a field that exists and may not be changed — the slug of a question
   *  that has already been authored. Shown rather than hidden, because "what is
   *  this one called" is the first thing anybody needs from this form. */
  disabled?: boolean
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-sm font-medium text-ash">{label}</span>
      {/* Named explicitly rather than by the wrapping <label>: with a hint
          under it, the label's text content is the label *and* the hint, and a
          screen reader would announce the whole paragraph as this field's
          name. */}
      <Input
        aria-label={label}
        size="sm"
        type={type}
        value={value}
        placeholder={placeholder}
        className={className}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
      />
      {hint && <span className="text-xs leading-relaxed text-ash/70">{hint}</span>}
    </label>
  )
}


/** The type-specific half of the form, one per answer shape.
 *
 *  `Record<QuestionType, …>` on purpose: a new member of the union with no
 *  editor here fails the build, which is the same guarantee `QUESTION_BOARDS`
 *  gives the play surface and the four backend registries give the loader. */
