import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'

const T = 'var(--color-court)'
const I = 'var(--color-void)'

/** A: wide scoreboard K — the brand letter, flat-sided, no curves to mistake. */
function MarkK({ size }: { size: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" aria-hidden>
      <rect width="32" height="32" rx="5" fill={T} />
      <path d="M8 7h4.4v18H8z" fill={I} />
      <path d="M24.4 7L16 15.2l8.8 9.8h-5.6l-7-8.1v-1.7L19 7z" fill={I} />
    </svg>
  )
}

/** B: the buzzer, side on — a dome on its base, with the press stroke above. */
function MarkBuzzer({ size }: { size: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" aria-hidden>
      <rect width="32" height="32" rx="5" fill={T} />
      <path d="M7 21a9 9 0 0 1 18 0z" fill={I} />
      <rect x="5" y="22.6" width="22" height="3.4" rx="1.7" fill={I} />
      <path d="M16 5.5v3.2M9.6 7.6l1.7 2.4M22.4 7.6l-1.7 2.4" stroke={I} strokeWidth="2.4" strokeLinecap="round" />
    </svg>
  )
}

/** C: the face-off — two solid wedges driving at each other. 1v1, nothing else. */
function MarkVersus({ size }: { size: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" aria-hidden>
      <rect width="32" height="32" rx="5" fill={T} />
      <path d="M6 6.5l8 9.5-8 9.5z" fill={I} />
      <path d="M26 6.5l-8 9.5 8 9.5z" fill={I} />
    </svg>
  )
}

/** D: the down — a heavy chevron driven onto the scoreboard bar. */
function MarkDown({ size }: { size: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" aria-hidden>
      <rect width="32" height="32" rx="5" fill={T} />
      <path d="M6.8 8.4l9.2 8.2 9.2-8.2" stroke={I} strokeWidth="4.2" strokeLinecap="square" fill="none" />
      <rect x="6" y="21.2" width="20" height="4.2" rx="1" fill={I} />
    </svg>
  )
}

/** Current: the ring and dot — reads as a camera lens. */
function MarkCurrent({ size }: { size: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" aria-hidden>
      <rect width="32" height="32" rx="5" fill={T} />
      <path d="M23.5 9.5a9.5 9.5 0 1 0 2.2 4.2" stroke={I} strokeWidth="2.8" strokeLinecap="round" />
      <circle cx="16" cy="16" r="4.4" fill={I} />
    </svg>
  )
}

const marks = [
  ['Current (camera)', MarkCurrent],
  ['A — Scoreboard K', MarkK],
  ['B — Buzzer', MarkBuzzer],
  ['C — Face-off', MarkVersus],
  ['D — Down', MarkDown],
] as const

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <div className="flex flex-col gap-5 p-4">
      {marks.map(([name, M]) => (
        <div key={name} className="flex flex-col gap-2 rounded-card border border-chalk/10 bg-panel/50 p-3">
          <p className="font-display text-xs font-bold uppercase tracking-wide text-ash">{name}</p>
          <div className="flex items-end gap-4">
            <M size={16} />
            <M size={24} />
            <M size={32} />
            <M size={56} />
          </div>
          <div className="flex items-center gap-2 border-t border-chalk/10 pt-2">
            <M size={30} />
            <span className="text-headline flex items-center text-2xl leading-none">
              <span className="text-chalk">KNOW</span>
              <span className="text-court">DOWN</span>
            </span>
          </div>
        </div>
      ))}
    </div>
  </StrictMode>,
)
