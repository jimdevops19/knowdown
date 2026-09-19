import { describe, expect, it, vi, afterEach } from 'vitest'
import { act, render, screen } from '@testing-library/react'
import { PreQuestionInfo } from './PreQuestionInfo'
import { useInstantPassed } from '../../hooks/useInstantPassed'
import { QUESTION_READ_DELAY_MS } from '../../lib/config'

/*
 * The task screen, and the boundary that dismisses it.
 *
 * What is checked here is the *arithmetic a match does*, not the markup: the
 * server sends one stamp (when the clock starts) and this client splits the
 * window in front of it into "state the task" and "read the question" by
 * subtracting the ordinary read delay back off. Getting that subtraction
 * backwards would either hold the instruction up over a question whose clock
 * is already running, or flash the question through it — so the harness below
 * derives the boundary exactly the way `MatchPage` does.
 */
function Harness({ seenAt, text }: { seenAt: number; text: string }) {
  const done = useInstantPassed(text ? seenAt - QUESTION_READ_DELAY_MS : null)
  return done ? <p>the question</p> : <PreQuestionInfo text={text} />
}

afterEach(() => {
  vi.useRealTimers()
})

describe('PreQuestionInfo', () => {
  it('holds the task up alone, then gives way to the question with the read delay still to come', () => {
    vi.useFakeTimers()
    const seenAt = Date.now() + QUESTION_READ_DELAY_MS + 2_500

    render(<Harness seenAt={seenAt} text="Click to order from earliest to latest" />)

    expect(screen.getByText('Click to order from earliest to latest')).toBeInTheDocument()
    expect(screen.queryByText('the question')).not.toBeInTheDocument()

    // One tick short of the boundary: still the instruction, because the whole
    // point is that the question is not on screen behind it.
    act(() => void vi.advanceTimersByTime(2_499))
    expect(screen.queryByText('the question')).not.toBeInTheDocument()

    act(() => void vi.advanceTimersByTime(1))
    expect(screen.getByText('the question')).toBeInTheDocument()
    // And the clock has not started: the reading beat the question would have
    // had anyway is still ahead of it, which is what "added, not taken out"
    // means in the one place a player could notice.
    expect(Date.now()).toBeLessThan(seenAt)
  })

  it('never appears for a question that states no task', () => {
    const seenAt = Date.now() + QUESTION_READ_DELAY_MS

    render(<Harness seenAt={seenAt} text="" />)

    expect(screen.getByText('the question')).toBeInTheDocument()
  })

  it('is over before it starts for a reconnect landing mid-question', () => {
    // The boundary is an absolute instant derived from the server's stamp, not
    // a duration started when this client mounted — so a player rejoining
    // eight seconds into a question is not shown the instruction again over a
    // board they are already answering.
    const seenAt = Date.now() - 8_000

    render(<Harness seenAt={seenAt} text="Click to order from earliest to latest" />)

    expect(screen.getByText('the question')).toBeInTheDocument()
  })
})
