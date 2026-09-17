import { Fragment, type ComponentType } from 'react'
import type { PlayQuestion, QuestionType } from '../../lib/api/types'
import { LevelChip } from '../../components/LevelChip'
import { SingleAnswerBoard } from './boards/SingleAnswerBoard'
import { ImageAnswerBoard } from './boards/ImageAnswerBoard'
import { MultipleAnswerBoard } from './boards/MultipleAnswerBoard'
import { TrueFalseBoard } from './boards/TrueFalseBoard'
import { FreeTextBoard } from './boards/FreeTextBoard'
import { OrderingBoard } from './boards/OrderingBoard'
import { MatrixBoard } from './boards/MatrixBoard'
import type { BoardProps } from './boards/types'

/*
 * One question, whatever shape it is.
 *
 * `QUESTION_BOARDS` is this app's copy of the registry the backend keeps four
 * of — `models.QUESTION_MODELS`, `schemas.answers.ANSWER_SUBMISSIONS`,
 * `services.evaluation.ANSWER_EVALUATORS` and
 * `api.serializers.QUESTION_SERIALIZERS`. Over there a type can be stored,
 * validated, scored and shown, and a test walks all four so none of them can be
 * the one that was forgotten. This is the fifth: a type can also be *played*.
 *
 * The gap is checked at compile time rather than by a test. `Record<QuestionType,
 * …>` makes a missing entry a type error, so a question type added to
 * `lib/api/types.ts` cannot reach production as a blank screen mid-match — the
 * build fails instead. That is the same trade the backend makes by raising at
 * import: refuse to start, rather than start and fail on somebody's question.
 *
 * The dispatch is by lookup rather than a `switch`, for the same reason it is a
 * registry on the other side: adding a type should be one line in one map, not
 * an edit to a control-flow statement that also has to be found.
 */
const QUESTION_BOARDS: Record<QuestionType, ComponentType<BoardProps<never>>> = {
  'single-answer': SingleAnswerBoard,
  'image-answer': ImageAnswerBoard,
  'multiple-answer': MultipleAnswerBoard,
  'true-false': TrueFalseBoard,
  'free-text': FreeTextBoard,
  ordering: OrderingBoard,
  matrix: MatrixBoard,
} as Record<QuestionType, ComponentType<BoardProps<never>>>

export function QuestionBoard(props: BoardProps<PlayQuestion> & { revealOptions: boolean }) {
  const { question, revealOptions, ...rest } = props
  const boardProps = { question, ...rest }
  const Board = QUESTION_BOARDS[question.type]

  // Unreachable through the type system, and handled anyway: this component
  // renders a payload that came off a socket, and a server deployed ahead of
  // this client can send a type it has never heard of. A player mid-match sees
  // a question they cannot answer either way — but "we don't know how to show
  // this one" is a far better ten seconds than a blank white screen.
  if (!Board) {
    return (
      <p className="rounded-tile border border-wrong/40 bg-wrong/10 p-4 text-sm text-wrong">
        This question needs a newer version of the app. Reload to update.
      </p>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Keyed on the question too, so the word-by-word reveal replays for
          every new question rather than sitting fully revealed because React
          reused the same DOM nodes underneath it. */}
      <QuestionPrompt key={question.id} question={question} />
      {/* Held back until the read delay has passed — the whole point of the
          fixed display order (text, then a beat to read it, then the
          options and the clock together) is that the player's attention has
          nowhere to go but the question until there is something to answer.
          Keyed on the question, so every question gets a *fresh* board rather
          than the previous one with its state reset by an effect. The boards
          that accumulate a working answer — ticks, an order, a grid of cells —
          would otherwise each need to notice the question changed underneath
          them, and any one of them forgetting would carry a half-built answer
          into the next question. Remounting makes that structurally impossible. */}
      {revealOptions && (
        <div className="motion-safe:animate-slide-up">
          <Board key={question.id} {...(boardProps as BoardProps<never>)} />
        </div>
      )}
    </div>
  )
}

/**
 * The question itself: its difficulty, its text, and its illustration if it has
 * one.
 *
 * The heading sizes down rather than up on a phone — unusual, and deliberate.
 * The prompt is competing for vertical space with the answer tiles, and a tile
 * pushed below the fold is a tile the clock runs out on. What has to be
 * biggest on a phone is the thing being *tapped*, not the thing being read.
 */
function QuestionPrompt({ question }: { question: PlayQuestion }) {
  const words = question.description.split(' ')
  // The whole line reveals in ~0.4s regardless of length — a short question
  // gets a leisurely per-word beat, a long one compresses the stagger rather
  // than blowing past the budget. Capped so a short question still reads as
  // word-by-word rather than one long fade.
  const stagger = words.length > 1 ? Math.min(400 / words.length, 45) : 0

  return (
    <div className="flex flex-col gap-3">
      <LevelChip level={question.level} className="self-start" />
      <h2 className="text-balance font-display text-xl font-bold leading-snug text-chalk sm:text-2xl">
        {words.map((word, index) => (
          // The space is a plain text node alongside the span, not inside it —
          // that's what keeps it a normal line-wrap point (an inline-block
          // word glued straight to the next would refuse to wrap on a phone)
          // and what keeps `textContent` reading as the real sentence, spaces
          // included, for anything downstream that reads the question by text.
          <Fragment key={index}>
            <span
              className="inline-block motion-safe:animate-word-in"
              style={{ animationDelay: `${index * stagger}ms` }}
            >
              {word}
            </span>
            {index < words.length - 1 ? ' ' : ''}
          </Fragment>
        ))}
      </h2>
      {question.image && (
        <img
          src={question.image}
          // The illustration is *of the question*, and the backend has no
          // caption for it, so a made-up alt would be worse than none: the
          // question text above already says what is being asked. Empty alt
          // marks it decorative and keeps a screen reader from announcing a
          // filename.
          alt=""
          className="max-h-40 w-full rounded-tile object-contain sm:max-h-56"
        />
      )}
    </div>
  )
}
