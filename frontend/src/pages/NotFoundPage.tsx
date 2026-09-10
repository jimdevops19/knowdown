import { Link } from 'react-router-dom'
import { Button } from '../components/Button'
import { LogoMark } from '../components/Logo'

/** 404 — a URL that doesn't route. */
export function NotFoundPage() {
  return (
    <div className="flex flex-col items-center gap-5 py-16 text-center">
      <LogoMark size={56} className="opacity-60" />
      <div>
        <h1 className="font-display text-4xl font-bold text-chalk">404</h1>
        <p className="mt-2 text-ash">Nothing here. Nobody buzzed in.</p>
      </div>
      <Button as={Link} to="/" variant="secondary">
        Back home
      </Button>
    </div>
  )
}
