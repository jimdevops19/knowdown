import { Link, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Check, Clock, Play, X } from 'lucide-react'
import { getMatch } from '../lib/api/endpoints'
import { queryKeys } from '../lib/query/queryClient'
import { useAuth } from '../features/auth/useAuth'
import { Avatar } from '../components/Avatar'
import { Button } from '../components/Button'
import { Card } from '../components/Card'
import { AnswerKeyRow } from '../features/matches/answerKey/AnswerKeyRow'
import { RevealCell } from '../features/matches/answerKey/RevealCell'
import { describeSubmission } from '../features/matches/answerKey/submissions'
import { LevelChip } from '../components/LevelChip'
import { SectionHeading } from '../components/SectionHeading'
import { StatusBadge } from '../components/StatusBadge'
import { ErrorState, Loading } from '../components/states'
import { Table, TableBody, TableCell, TableHead, TableHeaderCell, TableRow } from '../components/Table'
import { formatDateTime, formatResponseTime } from '../lib/format'
import type {
  MatchupDetail,
  MatchupQuestionRecord,
  PlayQuestion,
  PlayerAnswerRecord,
} from '../lib/api/types'

/*
 * `/matches/:id` — the box score, question by question.
 *
 * Scoped to its two players; anybody else asking gets a 403. What it shows over
 * the history row is the board each question was played on — the *same*
 * play-time payload the socket sent while the clock was running, so this screen
 * inherits the anti-cheat guarantee rather than re-deciding it — plus each
 * side's own submission and verdict.
 *
 * **This is the one screen in the app that shows the right answer**, and it is
 * the platform's single deliberate exception to "no payload names a correct
 * answer" — see `apps.questions.api.reveal`, which is a module apart from the
 * anti-cheat surface rather than a hole punched in it. A box score read after
 * the whistle by the two people who just played is a post-mortem, and "you got
 * it wrong" with no way to find out what was right is a scoreboard pretending
 * to be one.
 *
 * The exception is paid for and it is worth knowing the price: a question whose
 * key somebody has read can be dealt again, to an opponent who has not. What
 * keeps that bounded is the endpoint, not this component — it refuses a live
 * match and refuses anyone who did not play in it — so a screen reusing
 * `answer_key` anywhere else would be spending a budget it did not earn.
 *
 * Long answers are truncated **server-side**: a grid square listing five names
 * out of twenty-two has seventeen the client was never sent. "… and 17 more" is
 * a count, not a fold.
 *
 * The answers map is keyed by **display name**, which is the backend's shape —
 * so finding your own row means looking yourself up by name, not by id.
 */
export function MatchDetailPage() {
  const { id = '' } = useParams()
  const { user } = useAuth()

  const match = useQuery({
    queryKey: queryKeys.matches.detail(id),
    queryFn: () => getMatch(id),
    enabled: !!id,
  })

  if (match.isLoading) return <Loading label="Loading the box score…" />
  if (match.isError) return <ErrorState error={match.error} />
  if (!match.data) return null

  const myName = user?.player_name ?? ''

  return (
    <div className="flex flex-col gap-5">
      <Scoreline match={match.data} myPlayerId={user?.player_id ?? null} />

      <section className="flex flex-col gap-3">
        <SectionHeading>Question by question</SectionHeading>
        {match.data.questions.map((record) => (
          <QuestionRecord key={record.order} record={record} myName={myName} />
        ))}
        {match.data.questions.length === 0 && (
          <p className="text-sm text-ash">
            This match ended before a question was played out.
          </p>
        )}
      </section>

      {/* Reserves the room `BackToPlayingBar` takes out of the flow by going
          fixed, so the last question row never ends up parked behind it. */}
      <div aria-hidden className="h-20" />
      <BackToPlayingBar categorySlug={match.data.category} />
    </div>
  )
}

/*
 * Pinned to the foot of the *viewport*, not just this page's content column —
 * a box score can run many screens of question-by-question rows, and "play
 * again" shouldn't cost a scroll back to the top to reach.
 *
 * Fixed rather than sticky: sticky stays inside its own ancestor's width, and
 * that ancestor is `<main>`'s `max-w-5xl` column, which on a wide desk
 * viewport leaves the bar looking stranded in the middle of the window
 * instead of spanning it. Fixed with `inset-x-0` spans the full window; the
 * inner row keeps the page's own `max-w-5xl` gutter so the button still lines
 * up under the content above it rather than drifting to the true edges.
 *
 * `bottom` tracks `--nav-bar-inset` (see index.css) so it stacks above the
 * fixed phone tab bar instead of landing behind it; on desk that variable is
 * 0 and the bar sits flush to the window edge.
 */
function BackToPlayingBar({ categorySlug }: { categorySlug: string }) {
  return (
    <div
      className="fixed inset-x-0 z-20 border-t border-chalk/10 bg-void px-safe"
      style={{ bottom: 'var(--nav-bar-inset)' }}
    >
      <div className="mx-auto w-full max-w-5xl py-3">
        <Button as={Link} to={`/play/${categorySlug}`} size="full" variant="primary">
          <Play size={18} aria-hidden />
          Back to playing
        </Button>
      </div>
    </div>
  )
}

function Scoreline({ match, myPlayerId }: { match: MatchupDetail; myPlayerId: string | null }) {
  const drew = !match.players.some((side) => side.is_winner)
  return (
    <Card className="flex flex-col gap-4 p-5">
      <div className="flex items-center justify-between gap-2">
        <span className="font-display text-sm uppercase tracking-wide text-ash">
          {match.category}
        </span>
        {/* Unrated outranks the rest: "abandoned but it still counted" and a
            question count both assume the thing a reader of an old match most
            needs to know is settled. A match played in a multi-category room
            moved nobody (`Room.is_rated`), and nothing else on this page says
            so. */}
        {!match.is_ranked ? (
          <StatusBadge tone="neutral">Unrated</StatusBadge>
        ) : drew ? (
          <StatusBadge tone="draw">Draw</StatusBadge>
        ) : match.outcome === 'abandoned' ? (
          <StatusBadge tone="warn">Abandoned · still ranked</StatusBadge>
        ) : (
          <StatusBadge tone="neutral">{match.question_count} questions</StatusBadge>
        )}
      </div>

      <div className="flex items-stretch gap-3">
        {match.players.map((side) => (
          <div
            key={side.player.id}
            className={`flex min-w-0 flex-1 flex-col items-center gap-2 rounded-tile border p-3 ${
              side.is_winner ? 'border-correct/50 bg-correct/8' : 'border-chalk/8'
            }`}
          >
            <Link to={`/players/${side.player.display_name}`}>
              <Avatar
                name={side.player.display_name}
                avatarUrl={side.player.avatar_url}
                size={44}
                ring={side.is_winner}
              />
            </Link>
            <span className="w-full truncate text-center text-sm font-medium text-chalk">
              {side.player.display_name}
              {side.player.id === myPlayerId && <span className="ml-1 text-volt">(you)</span>}
            </span>
            <span
              className={`nums font-display text-3xl font-bold leading-none ${
                side.is_winner ? 'text-correct' : 'text-ash'
              }`}
            >
              {side.score}
            </span>
            <span className="nums text-xs text-ash">
              {side.correct_answers} correct · {formatResponseTime(side.total_answer_time_ms)} total
            </span>
          </div>
        ))}
      </div>

      <p className="text-center text-xs text-ash">{formatDateTime(match.completed_at)}</p>
    </Card>
  )
}

function QuestionRecord({ record, myName }: { record: MatchupQuestionRecord; myName: string }) {
  const mine = record.answers[myName] ?? null
  const theirs = Object.entries(record.answers).find(([name]) => name !== myName)

  return (
    <Card className="flex flex-col gap-3 p-4">
      <div className="flex items-center gap-2">
        <span className="font-display text-xs font-bold uppercase tracking-wider text-ash">
          Q{record.order}
        </span>
        <LevelChip level={record.question.level} />
        {/* Why the match ran past the length the header states: the scores
            were level, so the server dealt one more. */}
        {record.is_tiebreaker && <StatusBadge tone="warn">Tie breaker</StatusBadge>}
      </div>

      <p className="font-medium text-chalk">{record.question.description}</p>

      <Table>
        <TableHead>
          <TableHeaderCell>Player</TableHeaderCell>
          <TableHeaderCell>Answer</TableHeaderCell>
          <TableHeaderCell align="right">Time</TableHeaderCell>
          <TableHeaderCell align="right">Points</TableHeaderCell>
        </TableHead>
        <TableBody>
          <AnswerRow label="You" answer={mine} question={record.question} />
          <AnswerRow
            label={theirs?.[0] ?? 'Rival'}
            answer={theirs?.[1] ?? null}
            question={record.question}
          />
          {record.answer_key && (
            <AnswerKeyRow
              question={record.question}
              answerKey={record.answer_key}
              mine={mine}
            />
          )}
        </TableBody>
      </Table>
    </Card>
  )
}

function AnswerRow({
  label,
  answer,
  question,
}: {
  label: string
  answer: PlayerAnswerRecord | null
  question: PlayQuestion
}) {
  // No record at all means the clock ran out on them. That is a different thing
  // from a wrong answer, and worth showing as one — the API distinguishes them
  // by the absence of a row, and so does this.
  if (!answer) {
    return (
      <TableRow>
        <TableCell className="text-ash">{label}</TableCell>
        <TableCell>
          <span className="flex items-center gap-1.5 text-idle">
            <Clock size={14} aria-hidden />
            Out of time
          </span>
        </TableCell>
        <TableCell align="right" className="text-ash">
          —
        </TableCell>
        <TableCell align="right" className="text-ash">
          —
        </TableCell>
      </TableRow>
    )
  }

  const partial = !answer.is_correct && answer.score > 0
  // The verdict is the tone and the icon; the cell says what they actually put.
  // A row reading only "Wrong" answers "did they take the question" and not
  // "what did they say", and the second is the one you re-read a box score for.
  // Partial credit keeps its number, because on a grid "60% right" is the
  // finding and the fill is the detail behind it.
  const tone = answer.is_correct ? 'text-correct' : partial ? 'text-gold' : 'text-wrong'

  return (
    <TableRow>
      <TableCell className="text-ash">{label}</TableCell>
      <TableCell>
        <div className="flex items-center gap-2">
          <RevealCell
            reveal={describeSubmission({ question, submitted: answer.submitted })}
            tone={tone}
            icon={
              answer.is_correct ? (
                <Check size={14} className="shrink-0" aria-hidden />
              ) : (
                <X size={14} className="shrink-0" aria-hidden />
              )
            }
          />
          {partial && (
            <span className="nums shrink-0 text-xs text-ash">
              {Math.round(answer.score * 100)}%
            </span>
          )}
        </div>
      </TableCell>
      <TableCell align="right" className="nums text-ash">
        {formatResponseTime(answer.response_time_ms)}
      </TableCell>
      <TableCell align="right" className="nums text-ash">
        +{answer.points}
      </TableCell>
    </TableRow>
  )
}
