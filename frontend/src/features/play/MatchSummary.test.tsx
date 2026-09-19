import { describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MatchSummary } from './MatchSummary'
import * as endpoints from '../../lib/api/endpoints'
import type { MatchupDetail } from '../../lib/api/types'
import type { MatchCompletedMessage } from '../../lib/realtime'

/*
 * What the end of a match offers next — the two ways out, and where each goes.
 *
 * Only the destinations are worth a test: the button that sends a player back
 * into a queue has to send them into the room they just played, and the box
 * score is the only thing that actually knows which that was (`?from=` is a
 * hint off the URL, and a reconnect or a shared link arrives without one).
 */
const COMPLETED: MatchCompletedMessage = {
  type: 'match.completed',
  winner_player_id: 'me',
  scores: { me: 120, them: 80 },
  outcome: 'played',
}

const BOX_SCORE = {
  id: 'm-1',
  category: 'nba',
  room: 'nba-room-finals',
  question_count: 3,
  status: 'completed',
  outcome: 'played',
  started_at: null,
  completed_at: null,
  players: [],
  questions: [],
} as unknown as MatchupDetail

function renderSummary({
  roomSlug,
  boxScore = BOX_SCORE,
}: {
  roomSlug: string | null
  boxScore?: MatchupDetail
}) {
  vi.spyOn(endpoints, 'getMatch').mockResolvedValue(boxScore)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <MatchSummary
          matchupId="m-1"
          completed={COMPLETED}
          myPlayerId="me"
          roomSlug={roomSlug}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('MatchSummary', () => {
  it('plays again in the room the match was actually played in', async () => {
    // No `?from=` at all — a reconnect, or a link into the match.
    renderSummary({ roomSlug: null })
    const again = await screen.findByRole('link', { name: /Play again/ })
    expect(again).toHaveAttribute('href', '/play/nba-room-finals')
  })

  it('prefers the played room over the one named in the route', async () => {
    // The route's slug is what the button points at for the first frame — it
    // is there before the fetch — and the box score corrects it on arrival.
    renderSummary({ roomSlug: 'some-other-room' })
    expect(screen.getByRole('link', { name: /Play again/ })).toHaveAttribute(
      'href',
      '/play/some-other-room',
    )
    await waitFor(() =>
      expect(screen.getByRole('link', { name: /Play again/ })).toHaveAttribute(
        'href',
        '/play/nba-room-finals',
      ),
    )
  })

  it('offers the lobby as the other way out', async () => {
    renderSummary({ roomSlug: null })
    expect(screen.getByRole('link', { name: /Back to rooms/ })).toHaveAttribute('href', '/play')
  })

  it('offers only the lobby for a match with no room behind it', async () => {
    renderSummary({ roomSlug: null, boxScore: { ...BOX_SCORE, room: null } })
    expect(await screen.findByRole('link', { name: /Back to rooms/ })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /Play again/ })).not.toBeInTheDocument()
  })
})
