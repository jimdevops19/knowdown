import { Link, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Check, Clock, X } from 'lucide-react'
import { getMatch } from '../lib/api/endpoints'
import { queryKeys } from '../lib/query/queryClient'
import { useAuth } from '../features/auth/useAuth'
import { Avatar } from '../components/Avatar'
import { Card } from '../components/Card'
import { LevelChip } from '../components/LevelChip'
import { SectionHeading } from '../components/SectionHeading'
import { StatusBadge } from '../components/StatusBadge'
import { ErrorState, Loading } from '../components/states'
import { formatDateTime, formatResponseTime } from '../lib/format'
import type { MatchupDetail, MatchupQuestionRecord, PlayerAnswerRecord } from '../lib/api/types'

/*
 * `/matches/:id` — the box score, question by question.
 *
 * Scoped to its two players; anybody else asking gets a 403. What it shows over
 * the history row is the board each question was played on — the *same*
 * play-time payload the socket sent while the clock was running, so this screen
 * inherits the anti-cheat guarantee rather than re-deciding it — plus each
 * side's own submission and verdict.
 *
 * **Which means the right answer is not on this page either.** The API never
 * publishes an answer key, and a box score is not an exception to that: a
 * question you got wrong here can come up again in a later match, against
 * somebody who hasn't seen it. What you get is what you said, whether it was
 * right, and how long you took.
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
        {drew ? (
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
              side.is_winner ? 'border-gold/50 bg-gold/8' : 'border-white/8'
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
                side.is_winner ? 'text-gold' : 'text-ash'
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
      </div>

      <p className="font-medium text-chalk">{record.question.description}</p>

      <div className="flex flex-col gap-1.5">
        <AnswerLine label="You" answer={mine} />
        <AnswerLine label={theirs?.[0] ?? 'Rival'} answer={theirs?.[1] ?? null} />
      </div>
    </Card>
  )
}

function AnswerLine({ label, answer }: { label: string; answer: PlayerAnswerRecord | null }) {
  // No record at all means the clock ran out on them. That is a different thing
  // from a wrong answer, and worth showing as one — the API distinguishes them
  // by the absence of a row, and so does this.
  if (!answer) {
    return (
      <div className="flex items-center gap-2 text-sm text-idle">
        <Clock size={14} aria-hidden />
        <span className="w-20 shrink-0 truncate">{label}</span>
        <span>Out of time</span>
      </div>
    )
  }

  const partial = !answer.is_correct && answer.score > 0

  return (
    <div className="flex items-center gap-2 text-sm">
      {answer.is_correct ? (
        <Check size={14} className="shrink-0 text-correct" aria-hidden />
      ) : (
        <X size={14} className="shrink-0 text-wrong" aria-hidden />
      )}
      <span className="w-20 shrink-0 truncate text-ash">{label}</span>
      <span
        className={
          answer.is_correct ? 'text-correct' : partial ? 'text-gold' : 'text-wrong'
        }
      >
        {answer.is_correct ? 'Correct' : partial ? `${Math.round(answer.score * 100)}% right` : 'Wrong'}
      </span>
      <span className="nums ml-auto shrink-0 text-ash">
        {formatResponseTime(answer.response_time_ms)} · +{answer.points}
      </span>
    </div>
  )
}
