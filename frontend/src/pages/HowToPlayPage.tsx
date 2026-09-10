import { Link } from 'react-router-dom'
import { Clock, ListOrdered, Radar, Trophy, Users, WifiOff, Zap } from 'lucide-react'
import { Button } from '../components/Button'
import { Card } from '../components/Card'
import { SectionHeading } from '../components/SectionHeading'

/*
 * `/how-to-play` — the rules, in the order a new player meets them.
 *
 * Public, and deliberately so: the questions it answers are the ones that
 * decide whether a visitor signs up, so it cannot sit behind signing up.
 *
 * Everything here is a *behaviour of the server*, written down. That is the
 * discipline this page needs: a rules page that describes what the client does
 * is a page that goes stale the first time the backend is retuned. Where a
 * number appears it is one the backend owns (ten seconds, three-five-seven, the
 * speed floor), and it is named as the server's.
 */

const SECTIONS = [
  {
    icon: Radar,
    title: 'One pool, one opponent',
    body: 'Everyone online sits in the same queue for a category. When a second player joins, the two of you are paired immediately — there is no lobby, no invite and no choosing who you face.',
  },
  {
    icon: ListOrdered,
    title: '3, 5 or 7 questions',
    body: 'The length is drawn once per match, for both players, before the first question. Neither of you is told which it is — so there is no last question to save yourself for.',
  },
  {
    icon: Clock,
    title: 'Ten seconds each',
    body: "The clock is the server's. It stamps the question when it opens and closes it when time is up, and the response time it scores is measured against that stamp — not against anything your device reports.",
  },
  {
    icon: Zap,
    title: 'Right first, then fast',
    body: 'A wrong answer is worth nothing however quickly you gave it. A correct one is worth more the sooner it lands — but never less than half, so working a hard question out to the wire is not scored as a guess.',
  },
  {
    icon: Users,
    title: 'You see that they answered, not what',
    body: "When your opponent locks in, you're told — and nothing else. Whether they were right is held back until the question closes, because while your clock is running, that would be the answer.",
  },
  {
    icon: WifiOff,
    title: 'Dropping out',
    body: 'Lose connection and you get a short grace period to come back; reconnect and you resume on the question in progress, with the clock where it actually is. Stay away and your opponent takes the win — and it counts on the ladder exactly as a played-out match would.',
  },
  {
    icon: Trophy,
    title: 'The ladder',
    body: 'Each category has its own rating, and it moves once per match. Beat someone rated above you and you take more from them than they would have taken from you. A dead-level match — same points, same total time — is scored as a draw rather than being broken arbitrarily.',
  },
]

export function HowToPlayPage() {
  return (
    <div className="flex flex-col gap-6 pb-4">
      <header className="flex flex-col gap-2">
        <h1 className="font-display text-3xl font-bold text-chalk">How a match works</h1>
        <p className="text-ash">Seven things, and then you know the whole game.</p>
      </header>

      <div className="flex flex-col gap-3">
        {SECTIONS.map(({ icon: Icon, title, body }) => (
          <Card key={title} className="flex gap-4 p-5">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-court/15 text-court">
              <Icon size={19} aria-hidden />
            </span>
            <div className="min-w-0">
              <h2 className="font-display text-lg font-bold text-chalk">{title}</h2>
              <p className="mt-1 text-sm text-ash">{body}</p>
            </div>
          </Card>
        ))}
      </div>

      <section className="flex flex-col gap-3">
        <SectionHeading>A note on fairness</SectionHeading>
        <Card className="p-5">
          <p className="text-sm text-ash">
            The answer to a question is never sent to your browser while you're answering it — not
            hidden in the page, not in a network response, not anywhere. The server tells you
            whether <em>you</em> were right once the question closes, and never publishes the
            answer key itself, because the same question can come up again in somebody else's
            match.
          </p>
          <p className="mt-3 text-sm text-ash">
            Both players also see the options in the same order, drawn from the match rather than
            from either device — so the race is over the same board, and an option's position
            isn't something to memorise between matches.
          </p>
        </Card>
      </section>

      <Button as={Link} to="/" size="full">
        Find a match
      </Button>
    </div>
  )
}
