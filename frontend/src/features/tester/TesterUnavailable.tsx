import { Link } from 'react-router-dom'
import { Lock } from 'lucide-react'
import { Button } from '../../components/Button'
import { Card } from '../../components/Card'

/*
 * What `/tester` shows to everyone it is not for.
 *
 * It deliberately does not say *which* of the two gates turned you away — that
 * the tier never mounted the surface, or that your account is not staff. There
 * is no version of that sentence that helps the reader and does not also tell
 * an unauthorised one whether there is something here worth coming back for.
 *
 * It is also not a redirect. A maintainer who lands here after being signed out
 * and back in, or who opened the link on a tier that does not run the tester,
 * should be told what happened rather than silently deposited on the home page
 * wondering whether they typed the URL wrong.
 */
export function TesterUnavailable() {
  return (
    <Card className="mx-auto flex max-w-sm flex-col items-center gap-4 p-8 text-center">
      <Lock className="text-ash" size={24} aria-hidden />
      <p className="text-ash">
        The question tester isn't available on this account.
      </p>
      <Button as={Link} to="/" size="full" variant="secondary">
        Back home
      </Button>
    </Card>
  )
}
