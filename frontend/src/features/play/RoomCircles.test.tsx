import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { RoomCircles } from './RoomCircles'
import * as endpoints from '../../lib/api/endpoints'
import type { Room } from '../../lib/api/types'

/*
 * The lobby's two load-bearing behaviours — the rest of this component is
 * layout, which a test can only restate.
 *
 *  1. **A room is a link to its own queue.** The slug in that href is what the
 *     matchmaking socket is opened on, so a wrong one is a player queued
 *     somewhere else entirely.
 *  2. **A room says what is in it.** The name is under the disc, and the
 *     description (or, unauthored, the categories) is behind the tile's `i` —
 *     the only thing telling a player these rooms apart, so it has to be
 *     reachable rather than merely present in a title attribute.
 *  3. **A room that cannot fill its own shortest match is not tappable.**
 *     `select_room_questions` refuses such a draw server-side, so a link there
 *     is a queue that can only ever fail.
 *  4. **An unrated room says so before you join it.** A room drawing from
 *     more than one category moves no ladder (`Room.is_rated`), and whether
 *     the game counts is part of choosing which room to play.
 */

const ROOM: Room = {
  slug: 'nba-room-finals',
  name: 'Ring Chasing',
  description: 'June basketball only.',
  question_counts: [4, 5, 6],
  categories: [{ slug: 'nba', name: 'NBA', filter_tags: { topic: 'finals' } }],
  question_pool_size: 40,
  is_rated: true,
  logo: '',
  color: '',
}

function renderLobby(rooms: Room[]) {
  vi.spyOn(endpoints, 'listRooms').mockResolvedValue(rooms)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <RoomCircles />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('RoomCircles', () => {
  it('links a playable room to its own queue', async () => {
    renderLobby([ROOM])
    const link = await screen.findByRole('link', { name: /Ring Chasing/ })
    expect(link).toHaveAttribute('href', '/play/nba-room-finals')
  })

  it('names the room under its ball', async () => {
    renderLobby([ROOM])
    expect(await screen.findByText('Ring Chasing')).toBeInTheDocument()
  })

  it('keeps the description behind the info button', async () => {
    renderLobby([ROOM])
    const info = await screen.findByRole('button', { name: /What is in Ring Chasing/ })
    expect(screen.queryByText('June basketball only.')).not.toBeInTheDocument()
    await userEvent.click(info)
    expect(await screen.findByText('June basketball only.')).toBeInTheDocument()
  })

  it('falls back to the category names when a room has no description', async () => {
    renderLobby([{ ...ROOM, description: '' }])
    await userEvent.click(await screen.findByRole('button', { name: /What is in Ring Chasing/ }))
    expect(await screen.findByText('NBA')).toBeInTheDocument()
  })

  it('marks a room that moves no ladder', async () => {
    renderLobby([{ ...ROOM, is_rated: false }])
    expect(await screen.findByText('Unrated')).toBeInTheDocument()
  })

  it('says nothing about rating for an ordinary room', async () => {
    renderLobby([ROOM])
    await screen.findByRole('link', { name: /Ring Chasing/ })
    expect(screen.queryByText('Unrated')).not.toBeInTheDocument()
  })

  it('does not link a room with nothing to draw from', async () => {
    renderLobby([{ ...ROOM, question_pool_size: 3 }])
    expect(await screen.findByText('Empty')).toBeInTheDocument()
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
  })

  it('says so when the lobby is empty rather than rendering nothing', async () => {
    renderLobby([])
    expect(await screen.findByText(/No rooms are open/)).toBeInTheDocument()
  })
})
