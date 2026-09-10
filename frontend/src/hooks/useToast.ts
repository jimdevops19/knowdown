import { useContext } from 'react'
import { ToastContext, type ToastApi } from '../components/toastContext'

/*
 * The hook components use to raise a toast. Lives apart from <ToastProvider> so
 * that file stays a component file — a module exporting both a hook and a
 * component defeats React Fast Refresh, which is why the auth layer splits the
 * same way (features/auth/useAuth).
 *
 * Throws rather than no-oping without a provider: a silently swallowed toast is
 * an action whose only feedback vanished, which is the bug this exists to fix.
 */
export function useToast(): ToastApi {
  const api = useContext(ToastContext)
  if (!api) throw new Error('useToast must be used inside <ToastProvider>')
  return api
}
