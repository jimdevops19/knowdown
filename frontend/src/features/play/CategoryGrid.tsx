import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Play } from 'lucide-react'
import { listCategories } from '../../lib/api/endpoints'
import { queryKeys } from '../../lib/query/queryClient'
import { Card } from '../../components/Card'
import { ErrorState, Loading } from '../../components/states'
import type { Category } from '../../lib/api/types'

/*
 * The category picker: pick one, and it routes to `/play/:category` to queue.
 * Shared by the Home page and `/play` (Live), the only two screens that offer
 * it — one entry point, so the guest/guard behaviour described in router.tsx
 * only has to be right once.
 */
export function CategoryGrid() {
  const categories = useQuery({
    queryKey: queryKeys.categories.all,
    queryFn: listCategories,
    staleTime: Infinity,
  })

  if (categories.isLoading) return <Loading variant="cards" />
  if (categories.isError) return <ErrorState error={categories.error} />
  if (!categories.data) return null

  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {categories.data.map((category) => (
        <CategoryCard key={category.slug} category={category} />
      ))}
    </div>
  )
}

function CategoryCard({ category }: { category: Category }) {
  return (
    <Card
      as={Link}
      to={`/play/${category.slug}`}
      interactive
      edge="court"
      className="flex flex-col gap-3 p-5"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="font-display text-lg font-bold text-chalk">{category.name}</h3>
          <p className="mt-0.5 line-clamp-2 text-sm text-ash">{category.description}</p>
        </div>
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[6px] bg-court/20 text-court">
          <Play size={18} aria-hidden />
        </span>
      </div>
      <span className="font-display text-xs font-semibold uppercase tracking-[0.12em] text-volt">
        Find a match →
      </span>
    </Card>
  )
}
