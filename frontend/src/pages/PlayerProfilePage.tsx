import { useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { getPlayerProfile } from '../lib/api/endpoints'
import { queryKeys } from '../lib/query/queryClient'
import { useAuth } from '../features/auth/useAuth'
import { Avatar } from '../components/Avatar'
import { Card } from '../components/Card'
import { SectionHeading } from '../components/SectionHeading'
import { ErrorState, Loading } from '../components/states'
import { formatRecord, timeAgo, winRate } from '../lib/format'
import type { PlayerAchievement, Ranking } from '../lib/api/types'

/*
 * `/players/:displayName` — anybody's public profile, in one round trip.
 *
 * Public, and everything on it is public by construction: a name, a picture, a
 * rating per category played and the badges earned. There is no email address
 * on this page because there is none in the payload — `GET /auth/me/` is the
 * only endpoint in the API allowed to emit one, and a test on the backend walks
 * every serializer to keep that true.
 *
 * Looked up case-insensitively, matching the constraint behind the name, so
 * `/players/Kobe` and `/players/kobe` cannot be two different people.
 */
export function PlayerProfilePage() {
  const { displayName = '' } = useParams()
  const { user } = useAuth()

  const profile = useQuery({
    queryKey: queryKeys.players.profile(displayName),
    queryFn: () => getPlayerProfile(displayName),
    enabled: !!displayName,
  })

  if (profile.isLoading) return <Loading label="Loading profile…" />
  if (profile.isError) return <ErrorState error={profile.error} />
  if (!profile.data) return null

  const { display_name, avatar_url, rankings, badges } = profile.data
  const isMe = profile.data.id === user?.player_id

  return (
    <div className="flex flex-col gap-6">
      <header className="flex items-center gap-4">
        <Avatar name={display_name} avatarUrl={avatar_url} size={72} ring={isMe} />
        <div className="min-w-0">
          <h1 className="truncate font-display text-2xl font-bold text-chalk">{display_name}</h1>
          <p className="text-sm text-ash">
            {rankings.length === 0
              ? 'No ranked matches yet'
              : `Ranked in ${rankings.length} categor${rankings.length === 1 ? 'y' : 'ies'}`}
          </p>
        </div>
      </header>

      {rankings.length > 0 && (
        <section className="flex flex-col gap-3">
          <SectionHeading>Ratings</SectionHeading>
          <div className="grid gap-3 sm:grid-cols-2">
            {rankings.map((ranking) => (
              <RatingCard key={ranking.category} ranking={ranking} />
            ))}
          </div>
        </section>
      )}

      <section className="flex flex-col gap-3">
        <SectionHeading>Badges</SectionHeading>
        {badges.length === 0 ? (
          <p className="text-sm text-ash">
            {isMe ? "You haven't earned a badge yet." : 'No badges yet.'}
          </p>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {badges.map((badge) => (
              <BadgeCard key={badge.slug} badge={badge} />
            ))}
          </div>
        )}
      </section>
    </div>
  )
}

function RatingCard({ ranking }: { ranking: Ranking }) {
  return (
    <Card className="flex items-center justify-between gap-3 p-4">
      <div className="min-w-0">
        <p className="truncate font-medium text-chalk">{ranking.category_name}</p>
        <p className="nums text-sm text-ash">
          {formatRecord(ranking.wins, ranking.losses)} in {ranking.games_played} ·{' '}
          {winRate(ranking.wins, ranking.games_played)}
        </p>
      </div>
      <span className="nums shrink-0 font-display text-2xl font-bold text-gold">
        {ranking.rating}
      </span>
    </Card>
  )
}

function BadgeCard({ badge }: { badge: PlayerAchievement }) {
  return (
    <Card className="flex items-center gap-3 p-4" border="border-gold/25">
      {badge.icon_url ? (
        <img src={badge.icon_url} alt="" className="h-11 w-11 shrink-0 object-contain" />
      ) : (
        // A badge with no icon yet is still a badge. Its initial in a gold
        // roundel rather than a broken image or a blank square.
        <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-gold/15 font-display text-lg font-bold text-gold">
          {badge.name[0]?.toUpperCase()}
        </span>
      )}
      <div className="min-w-0">
        <p className="truncate font-medium text-chalk">{badge.name}</p>
        <p className="line-clamp-2 text-xs text-ash">{badge.description}</p>
        <p className="mt-0.5 text-xs text-ash/70">{timeAgo(badge.earned_at)}</p>
      </div>
    </Card>
  )
}
