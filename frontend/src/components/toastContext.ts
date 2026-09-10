import { createContext, type ReactNode } from 'react'

/*
 * The toast context and its vocabulary, kept apart from <ToastProvider> so that
 * component file exports only components — a file mixing the two breaks React
 * Fast Refresh. See Toast.tsx for the system and hooks/useToast for the hook
 * components actually call.
 */

export type ToastLevel = 'info' | 'success' | 'warning' | 'error'

export interface ToastOptions {
  /** Secondary line under the title — the detail, the API message, the "why". */
  description?: ReactNode
  /** Milliseconds on screen. `0` pins it until dismissed by hand. */
  duration?: number
  /**
   * Stable identity. Re-showing an existing id replaces that toast in place
   * instead of stacking a duplicate — for a repeated action that would
   * otherwise pile up.
   */
  id?: string
}

export interface Toast extends ToastOptions {
  id: string
  level: ToastLevel
  title: ReactNode
}

export interface ToastInput extends ToastOptions {
  level: ToastLevel
  title: ReactNode
}

export interface ToastApi {
  /** The general form — the only one taking a `level` and a custom id. */
  show: (toast: ToastInput) => string
  info: (title: ReactNode, options?: ToastOptions) => string
  success: (title: ReactNode, options?: ToastOptions) => string
  warning: (title: ReactNode, options?: ToastOptions) => string
  error: (title: ReactNode, options?: ToastOptions) => string
  dismiss: (id: string) => void
}

export const ToastContext = createContext<ToastApi | null>(null)
