import { CHALK, INK, holding, mascot, type BallKind } from './primitives'

/*
 * The forty-one marks a player can wear.
 *
 * ── The key is the contract ──────────────────────────────────────────────────
 * `key` is what the backend stores and the only part of this file that is
 * permanent. A drawing may be redrawn, a label may be reworded, a mark may
 * move between groups — none of that touches anybody's saved choice. Changing
 * a `key`, on the other hand, silently un-picks every player who chose it, so
 * treat the strings as append-only. (The same rule the question bank runs on;
 * see `backend/apps/questions/resources/`.)
 *
 * The list is mirrored as an allow-list in `apps/players/constants.py`, which
 * is what makes a bogus key a 400 rather than a blank avatar. Both files move
 * together or neither does.
 *
 * ── Three groups, and why the first sixteen have empty hands ─────────────────
 * The ball is what tells the groups apart. If every mascot held one it would
 * stop meaning anything, so the founding sixteen keep their hands free and
 * everything after them is holding.
 */
export interface Mark {
  /** Permanent. Stored on the player; never re-spell one. */
  key: string
  /** What the picker calls it. Free to change. */
  label: string
  /** The livery it holds, if it holds anything. Also the picker's filter. */
  ball: BallKind | null
  /** The body of a 64×64 `<svg>`. Built by `mascot()`, never hand-assembled. */
  svg: string
}

/* ── The founding sixteen — empty hands ──────────────────────────────────── */

const FOUNDERS: Mark[] = [
  {
    key: 'bulldog',
    label: 'Bulldog',
    ball: null,
    svg: mascot({
      fur: '#c9955f',
      ears: `<path d="M13 22c-3 8-2 14 2 17l7-9z" fill="#a97a46"/><path d="M51 22c3 8 2 14-2 17l-7-9z" fill="#a97a46"/>`,
      muzzle: `<ellipse cx="32" cy="42" rx="11" ry="8" fill="#e8c69b"/>`,
      extra: `<path d="M24 40h16" stroke="${INK}" stroke-width="2.6" stroke-linecap="round" fill="none"/>
              <ellipse cx="32" cy="38" rx="4" ry="3" fill="${INK}"/>
              <path d="M32 40v4M27 47c3 2 7 2 10 0" stroke="${INK}" stroke-width="2.4" fill="none" stroke-linecap="round"/>
              <path d="M12 21c6-5 34-5 40 0l-2 5c-9-4-27-4-36 0z" fill="#ff7a14"/>`,
    }),
  },
  {
    key: 'owl',
    label: 'Owl (the ref)',
    ball: null,
    svg: mascot({
      fur: '#8f6fc9',
      ears: `<path d="M16 20l6 8 4-9z" fill="#7a58b8"/><path d="M48 20l-6 8-4-9z" fill="#7a58b8"/>`,
      eyes: 'wide',
      extra: `<path d="M32 36l4 6h-8z" fill="#ffd24a"/>
              <path d="M18 44c4 4 24 4 28 0" fill="none" stroke="#7a58b8" stroke-width="2.6" stroke-linecap="round"/>
              <path d="M44 46l10 4" stroke="${CHALK}" stroke-width="2.4"/><circle cx="55" cy="51" r="5" fill="#ff7a14"/>`,
    }),
  },
  {
    key: 'shark',
    label: 'Shark',
    ball: null,
    svg: mascot({
      fur: '#5fd9ff',
      ears: `<path d="M32 8l9 12H23z" fill="#3fb4dd"/>`,
      eyes: 'dot',
      extra: `<path d="M18 40h28c-2 7-8 11-14 11s-12-4-14-11z" fill="${INK}"/>
              <path d="M22 40l3 5 3-5 3 5 3-5 3 5 3-5" fill="none" stroke="${CHALK}" stroke-width="2.2"/>`,
    }),
  },
  {
    key: 'bear',
    label: 'Bear',
    ball: null,
    svg: mascot({
      fur: '#a0703f',
      ears: `<circle cx="16" cy="20" r="7" fill="#8a5d31"/><circle cx="48" cy="20" r="7" fill="#8a5d31"/>`,
      muzzle: `<ellipse cx="32" cy="42" rx="9" ry="7" fill="#d9ab78"/>`,
      extra: `<ellipse cx="32" cy="38" rx="3.6" ry="2.8" fill="${INK}"/>
              <path d="M32 41v3M28 46c2.5 2 5.5 2 8 0" stroke="${INK}" stroke-width="2.3" fill="none" stroke-linecap="round"/>
              <path d="M11 22c7-8 35-8 42 0v3H11z" fill="#3ceda6"/><circle cx="32" cy="9" r="5" fill="#3ceda6"/>`,
    }),
  },
  {
    key: 'fox',
    label: 'Fox',
    ball: null,
    svg: mascot({
      fur: '#ff8c3a',
      ears: `<path d="M12 24l5-15 11 8z" fill="#e86f1c"/><path d="M52 24l-5-15-11 8z" fill="#e86f1c"/>`,
      muzzle: `<path d="M32 36c6 0 10 4 10 8s-5 7-10 7-10-3-10-7 4-8 10-8z" fill="${CHALK}"/>`,
      extra: `<ellipse cx="32" cy="39" rx="3.4" ry="2.6" fill="${INK}"/>
              <path d="M32 42v3" stroke="${INK}" stroke-width="2.2" stroke-linecap="round"/>
              <path d="M14 27h8M42 27h8" stroke="#5fd9ff" stroke-width="3.6" stroke-linecap="round"/>`,
    }),
  },
  {
    key: 'tiger',
    label: 'Tiger',
    ball: null,
    svg: mascot({
      fur: '#ffb020',
      ears: `<circle cx="15" cy="21" r="6.5" fill="#e59300"/><circle cx="49" cy="21" r="6.5" fill="#e59300"/>`,
      muzzle: `<ellipse cx="32" cy="42" rx="10" ry="7" fill="#fff0d0"/>`,
      extra: `<path d="M22 20l3 6M32 17v6M42 20l-3 6M16 34l-4-2M48 34l4-2" stroke="${INK}" stroke-width="3" stroke-linecap="round"/>
              <path d="M32 38l3 3h-6z" fill="${INK}"/>
              <path d="M32 41v3M26 45c4 3 8 3 12 0" stroke="${INK}" stroke-width="2.4" fill="none" stroke-linecap="round"/>`,
    }),
  },
  {
    key: 'goat',
    label: 'The GOAT',
    ball: null,
    svg: mascot({
      fur: '#e8e4dc',
      ears: `<path d="M14 18c-4-6-1-10 4-8 4 2 6 7 6 11z" fill="#cfc9be"/><path d="M50 18c4-6 1-10-4-8-4 2-6 7-6 11z" fill="#cfc9be"/>
             <ellipse cx="14" cy="30" rx="6" ry="3.5" fill="#cfc9be"/><ellipse cx="50" cy="30" rx="6" ry="3.5" fill="#cfc9be"/>`,
      eyes: 'dot',
      extra: `<ellipse cx="32" cy="42" rx="7" ry="6" fill="#cfc9be"/>
              <path d="M30 41h4M32 44v3" stroke="${INK}" stroke-width="2.2" stroke-linecap="round"/>
              <path d="M28 50c3-4 8 2 8 6" fill="none" stroke="#e8e4dc" stroke-width="3.5" stroke-linecap="round"/>
              <path d="M22 12h20l-2 6H24z" fill="#ffd24a"/>`,
    }),
  },
  {
    key: 'ram',
    label: 'Ram',
    ball: null,
    svg: mascot({
      fur: '#cfd7de',
      ears: `<path d="M13 24c-7 0-9 10-2 13 5 2 8-2 6-6" fill="#a9b4bd"/><path d="M51 24c7 0 9 10 2 13-5 2-8-2-6-6" fill="#a9b4bd"/>`,
      eyes: 'squint',
      extra: `<ellipse cx="32" cy="43" rx="8" ry="6" fill="#eef2f5"/>
              <path d="M29 42h6M32 45v3" stroke="${INK}" stroke-width="2.2" stroke-linecap="round"/>
              <path d="M18 18c5-5 23-5 28 0" fill="none" stroke="#ff7a14" stroke-width="4" stroke-linecap="round"/>`,
    }),
  },
  {
    key: 'penguin',
    label: 'Penguin',
    ball: null,
    svg: mascot({
      fur: '#1d3b52',
      eyes: 'squint',
      extra: `<ellipse cx="32" cy="40" rx="12" ry="12" fill="${CHALK}"/>
              <circle cx="26" cy="33" r="4.4" fill="${CHALK}"/><circle cx="38" cy="33" r="4.4" fill="${CHALK}"/>
              <circle cx="26.6" cy="33.4" r="2.2" fill="${INK}"/><circle cx="37.4" cy="33.4" r="2.2" fill="${INK}"/>
              <path d="M32 38l5 4-5 4-5-4z" fill="#ff7a14"/>
              <path d="M14 48c10 5 26 5 36 0l3 6c-13 6-29 6-42 0z" fill="#ff7a14"/>`,
    }),
  },
  {
    key: 'gorilla',
    label: 'Gorilla',
    ball: null,
    svg: mascot({
      fur: '#4a4f57',
      ears: `<circle cx="13" cy="33" r="6" fill="#3a3e45"/><circle cx="51" cy="33" r="6" fill="#3a3e45"/>`,
      muzzle: `<path d="M32 33c8 0 13 5 13 10s-6 9-13 9-13-4-13-9 5-10 13-10z" fill="#8b7b6b"/>`,
      eyes: 'squint',
      extra: `<circle cx="26" cy="29" r="4" fill="${CHALK}"/><circle cx="38" cy="29" r="4" fill="${CHALK}"/>
              <circle cx="26.6" cy="29.4" r="2" fill="${INK}"/><circle cx="37.4" cy="29.4" r="2" fill="${INK}"/>
              <path d="M28 40h8M25 47c5 3 9 3 14 0" stroke="${INK}" stroke-width="2.4" fill="none" stroke-linecap="round"/>`,
    }),
  },
  {
    key: 'rooster',
    label: 'Rooster',
    ball: null,
    svg: mascot({
      fur: '#f2f4f6',
      ears: `<path d="M22 16c2-6 6-6 7-1 2-5 6-5 7 0 2-4 6-3 6 2l-2 6H23z" fill="#ff5a4a"/>`,
      extra: `<path d="M32 37l8 5-8 5z" fill="#ffb020"/>
              <path d="M28 48c3 3 8 3 11-1" fill="none" stroke="#ff5a4a" stroke-width="3" stroke-linecap="round"/>
              <path d="M16 44c-4 3-4 7 0 9" fill="none" stroke="#ff5a4a" stroke-width="3"/>`,
    }),
  },
  {
    /* Named `ox`, not `bull`. This is the founding mark, and the later NBA-ish
       set has a bull of its own with a ball in hand — one picker cannot list
       two animals called Bull. The drawing never changed; the label did. */
    key: 'ox',
    label: 'Ox',
    ball: null,
    svg: mascot({
      fur: '#6b4a3a',
      ears: `<path d="M12 26c-6-4-8 4-4 8 3 3 7 2 8-2z" fill="#e8e4dc"/><path d="M52 26c6-4 8 4 4 8-3 3-7 2-8-2z" fill="#e8e4dc"/>`,
      muzzle: `<ellipse cx="32" cy="43" rx="10" ry="7" fill="#c4907a"/>`,
      eyes: 'squint',
      extra: `<ellipse cx="28" cy="42" rx="2.4" ry="3" fill="${INK}"/><ellipse cx="36" cy="42" rx="2.4" ry="3" fill="${INK}"/>
              <path d="M26 48c4 2 8 2 12 0" stroke="${INK}" stroke-width="2.4" fill="none" stroke-linecap="round"/>
              <circle cx="46" cy="49" r="4" fill="${CHALK}" opacity="0.7"/><circle cx="53" cy="46" r="2.6" fill="${CHALK}" opacity="0.5"/>`,
    }),
  },
  {
    key: 'eagle',
    label: 'Eagle',
    ball: null,
    svg: mascot({
      fur: '#f5f7f9',
      ears: `<path d="M32 14c-10 0-18 6-20 13l40 0c-2-7-10-13-20-13z" fill="#e2e7ec"/>`,
      eyes: 'squint',
      extra: `<path d="M32 36l7 6-7 6-7-6z" fill="#ffb020"/>
              <path d="M12 30c4-8 12-12 20-12s16 4 20 12" fill="none" stroke="#3a4a58" stroke-width="2.4"/>`,
    }),
  },
  {
    key: 'frog',
    label: 'Frog',
    ball: null,
    svg: mascot({
      fur: '#3ceda6',
      ears: `<circle cx="20" cy="18" r="9" fill="#3ceda6"/><circle cx="44" cy="18" r="9" fill="#3ceda6"/>
             <circle cx="20" cy="18" r="5.5" fill="${CHALK}"/><circle cx="44" cy="18" r="5.5" fill="${CHALK}"/>
             <circle cx="20" cy="18.5" r="2.6" fill="${INK}"/><circle cx="44" cy="18.5" r="2.6" fill="${INK}"/>`,
      eyes: 'squint',
      extra: `<path d="M18 38c4 8 24 8 28 0" fill="none" stroke="${INK}" stroke-width="3" stroke-linecap="round"/>
              <circle cx="22" cy="44" r="3" fill="#2bc98a"/><circle cx="42" cy="44" r="3" fill="#2bc98a"/>`,
    }),
  },
  {
    key: 'octopus',
    label: 'Octopus',
    ball: null,
    svg: mascot({
      fur: '#ff6b7f',
      eyes: 'wide',
      extra: `<path d="M14 46c0 6 3 10 5 12M23 50c-1 6 0 9 2 11M41 50c1 6 0 9-2 11M50 46c0 6-3 10-5 12"
                fill="none" stroke="#ff6b7f" stroke-width="5" stroke-linecap="round"/>
              <path d="M25 42c4 3 10 3 14 0" fill="none" stroke="${INK}" stroke-width="2.6" stroke-linecap="round"/>`,
    }),
  },
  {
    key: 'cat',
    label: 'Cat',
    ball: null,
    svg: mascot({
      fur: '#9aa4ad',
      ears: `<path d="M14 26l2-14 12 8z" fill="#7d868e"/><path d="M50 26l-2-14-12 8z" fill="#7d868e"/>`,
      muzzle: `<ellipse cx="32" cy="42" rx="9" ry="6" fill="#c3cbd2"/>`,
      extra: `<path d="M32 38l3 3h-6z" fill="${INK}"/>
              <path d="M32 41v2M28 45c2 2 6 2 8 0M28 45c-2 2-6 2-8 0" stroke="${INK}" stroke-width="2.2" fill="none" stroke-linecap="round"/>
              <path d="M12 40l8-2M12 46l8-3M52 40l-8-2M52 46l-8-3" stroke="${CHALK}" stroke-width="1.8" opacity="0.8"/>`,
    }),
  },
]

/* ── The second sixteen — ball in hand, four to a livery ─────────────────── */

const BALLERS: Mark[] = [
  {
    key: 'wolf',
    label: 'Wolf',
    ball: 'orange',
    svg: mascot({
      fur: '#7b8794',
      ears: `<path d="M13 25l3-13 11 7z" fill="#5f6b78"/><path d="M51 25l-3-13-11 7z" fill="#5f6b78"/>`,
      muzzle: `<path d="M32 36c6 0 11 4 11 8s-5 8-11 8-11-4-11-8 5-8 11-8z" fill="#cdd5dc"/>`,
      extra: `<path d="M32 39l3.4 3h-6.8z" fill="${INK}"/>
              <path d="M32 42v3M27 47c3 2.5 7 2.5 10 0" stroke="${INK}" stroke-width="2.2" fill="none" stroke-linecap="round"/>
              ${holding('#5f6b78', 'orange')}`,
    }),
  },
  {
    key: 'panda',
    label: 'Panda',
    ball: 'orange',
    svg: mascot({
      fur: '#f4f6f8',
      ears: `<circle cx="16" cy="20" r="7" fill="#1d2329"/><circle cx="48" cy="20" r="7" fill="#1d2329"/>`,
      muzzle: `<ellipse cx="32" cy="43" rx="8" ry="6" fill="#ffffff"/>`,
      eyes: 'dot',
      extra: `<ellipse cx="25" cy="31" rx="6" ry="7.5" fill="#1d2329" transform="rotate(-12 25 31)"/>
              <ellipse cx="39" cy="31" rx="6" ry="7.5" fill="#1d2329" transform="rotate(12 39 31)"/>
              <circle cx="25" cy="31" r="2.6" fill="${CHALK}"/><circle cx="39" cy="31" r="2.6" fill="${CHALK}"/>
              <ellipse cx="32" cy="40" rx="3.4" ry="2.6" fill="${INK}"/>
              <path d="M32 43v2.5M29 47c2 1.6 4 1.6 6 0" stroke="${INK}" stroke-width="2" fill="none" stroke-linecap="round"/>
              ${holding('#1d2329', 'orange')}`,
    }),
  },
  {
    key: 'lion',
    label: 'Lion',
    ball: 'orange',
    svg: mascot({
      fur: '#ffb347',
      ears: `<circle cx="32" cy="34" r="25" fill="#c2701a"/>
             <path d="M32 9v6M11 20l4 4M53 20l-4 4M7 34h6M57 34h-6M11 48l4-4M53 48l-4-4M32 59v-6" stroke="#c2701a" stroke-width="5" stroke-linecap="round"/>
             <circle cx="16" cy="24" r="5.5" fill="#e59300"/><circle cx="48" cy="24" r="5.5" fill="#e59300"/>`,
      muzzle: `<ellipse cx="32" cy="42" rx="10" ry="7" fill="#ffe0b0"/>`,
      extra: `<path d="M32 38l3.2 3.2h-6.4z" fill="${INK}"/>
              <path d="M32 41v3M26 45c4 3 8 3 12 0" stroke="${INK}" stroke-width="2.3" fill="none" stroke-linecap="round"/>
              ${holding('#c2701a', 'orange')}`,
    }),
  },
  {
    key: 'raccoon',
    label: 'Raccoon',
    ball: 'orange',
    svg: mascot({
      fur: '#96a0aa',
      ears: `<path d="M14 24l3-11 10 6z" fill="#767f88"/><path d="M50 24l-3-11-10 6z" fill="#767f88"/>`,
      muzzle: `<ellipse cx="32" cy="43" rx="8" ry="6" fill="#eef2f5"/>`,
      eyes: 'dot',
      extra: `<path d="M17 30c4-5 26-5 30 0-2 7-6 9-15 9s-13-2-15-9z" fill="#2c343b"/>
              <circle cx="25" cy="31" r="2.6" fill="${CHALK}"/><circle cx="39" cy="31" r="2.6" fill="${CHALK}"/>
              <path d="M32 40l2.8 2.6h-5.6z" fill="${INK}"/>
              <path d="M32 43v2.5" stroke="${INK}" stroke-width="2" stroke-linecap="round"/>
              ${holding('#767f88', 'orange')}`,
    }),
  },
  {
    key: 'husky',
    label: 'Husky',
    ball: 'aba',
    svg: mascot({
      fur: '#e3ebf1',
      ears: `<path d="M14 24l4-13 10 8z" fill="#4d5b66"/><path d="M50 24l-4-13-10 8z" fill="#4d5b66"/>`,
      muzzle: `<path d="M32 37c6 0 10 4 10 7s-4 7-10 7-10-3-10-7 4-7 10-7z" fill="#ffffff"/>`,
      extra: `<path d="M18 22c5-5 23-5 28 0-3 6-6 9-14 9s-11-3-14-9z" fill="#4d5b66"/>
              <circle cx="25" cy="32" r="4.4" fill="${CHALK}"/><circle cx="39" cy="32" r="4.4" fill="${CHALK}"/>
              <circle cx="25" cy="32.2" r="2.2" fill="#5fd9ff"/><circle cx="39" cy="32.2" r="2.2" fill="#5fd9ff"/>
              <path d="M32 39l3 2.8h-6z" fill="${INK}"/>
              <path d="M32 42v3M27 46c3 2.4 7 2.4 10 0" stroke="${INK}" stroke-width="2.1" fill="none" stroke-linecap="round"/>
              ${holding('#4d5b66', 'aba')}`,
    }),
  },
  {
    key: 'moose',
    label: 'Moose',
    ball: 'aba',
    svg: mascot({
      fur: '#8a6244',
      ears: `<path d="M17 22c-7-2-11-8-9-13 4 0 6 2 8 5 1-4 3-6 6-7 2 4 1 8-1 11z" fill="#c9a06a"/>
             <path d="M47 22c7-2 11-8 9-13-4 0-6 2-8 5-1-4-3-6-6-7-2 4-1 8 1 11z" fill="#c9a06a"/>
             <ellipse cx="12" cy="32" rx="4.5" ry="3" fill="#6f4c33"/><ellipse cx="52" cy="32" rx="4.5" ry="3" fill="#6f4c33"/>`,
      eyes: 'dot',
      muzzle: `<ellipse cx="32" cy="44" rx="10" ry="8" fill="#6f4c33"/>`,
      extra: `<ellipse cx="28.5" cy="42" rx="1.6" ry="2.2" fill="${INK}"/><ellipse cx="35.5" cy="42" rx="1.6" ry="2.2" fill="${INK}"/>
              <path d="M27 48c3.5 2 7 2 10 0" stroke="${INK}" stroke-width="2.1" fill="none" stroke-linecap="round"/>
              ${holding('#6f4c33', 'aba')}`,
    }),
  },
  {
    /* Named `falcon`, not `hawk`, for the reason `ox` is not `bull`: the later
       set has a hawk of its own. Same bird as always, different word. */
    key: 'falcon',
    label: 'Falcon',
    ball: 'aba',
    svg: mascot({
      fur: '#8f5326',
      ears: `<path d="M32 12c-12 0-20 7-22 16l44 0c-2-9-10-16-22-16z" fill="#6d3d17"/>`,
      eyes: 'dot',
      muzzle: `<path d="M20 36c3 9 7 14 12 14s9-5 12-14z" fill="#f0e2d0"/>`,
      extra: `<circle cx="25" cy="31" r="4.4" fill="${CHALK}"/><circle cx="39" cy="31" r="4.4" fill="${CHALK}"/>
              <circle cx="25.6" cy="31.2" r="2.2" fill="${INK}"/><circle cx="38.4" cy="31.2" r="2.2" fill="${INK}"/>
              <path d="M17 24l12 4-12 3z" fill="#5e3316"/><path d="M47 24l-12 4 12 3z" fill="#5e3316"/>
              <path d="M28.5 36h7l-1.5 6c-1 3.5-3 3.5-4 0z" fill="#ffb020"/>
              <path d="M32 42c2.2 0 3 2.4 1.6 4.2-1.2 1.4-3.2.2-3-2.2z" fill="#e08c00"/>
              ${holding('#6d3d17', 'aba')}`,
    }),
  },
  {
    key: 'boar',
    label: 'Boar',
    ball: 'aba',
    svg: mascot({
      fur: '#6e5a4e',
      ears: `<path d="M15 23l2-10 9 7z" fill="#56463d"/><path d="M49 23l-2-10-9 7z" fill="#56463d"/>`,
      muzzle: `<ellipse cx="32" cy="43" rx="9" ry="7" fill="#c08a80"/>`,
      eyes: 'squint',
      extra: `<ellipse cx="28.5" cy="42.5" rx="1.8" ry="2.4" fill="${INK}"/><ellipse cx="35.5" cy="42.5" rx="1.8" ry="2.4" fill="${INK}"/>
              <path d="M24 46c-3 1-4-3-2-5" fill="none" stroke="${CHALK}" stroke-width="2.6" stroke-linecap="round"/>
              <path d="M40 46c3 1 4-3 2-5" fill="none" stroke="${CHALK}" stroke-width="2.6" stroke-linecap="round"/>
              <path d="M28 18l2 6M32 16v6M36 18l-2 6" stroke="#56463d" stroke-width="2.6" stroke-linecap="round"/>
              ${holding('#56463d', 'aba')}`,
    }),
  },
  {
    key: 'polar-bear',
    label: 'Polar bear',
    ball: 'white',
    svg: mascot({
      fur: '#eef5fa',
      ears: `<circle cx="16" cy="21" r="6.5" fill="#cfe0ea"/><circle cx="48" cy="21" r="6.5" fill="#cfe0ea"/>`,
      muzzle: `<ellipse cx="32" cy="43" rx="9" ry="7" fill="#ffffff"/>`,
      extra: `<ellipse cx="32" cy="39.5" rx="3.6" ry="2.8" fill="${INK}"/>
              <path d="M32 42.5v3M28 47c2.5 2 5.5 2 8 0" stroke="${INK}" stroke-width="2.2" fill="none" stroke-linecap="round"/>
              ${holding('#cfe0ea', 'white')}`,
    }),
  },
  {
    key: 'dolphin',
    label: 'Dolphin',
    ball: 'white',
    svg: mascot({
      fur: '#7fb4dd',
      ears: `<path d="M32 8c6 4 9 9 9 14H24c1-6 4-10 8-14z" fill="#5f97c4"/>`,
      eyes: 'dot',
      muzzle: `<path d="M32 38c8 0 13 3 13 6s-6 6-13 6-13-3-13-6 5-6 13-6z" fill="#cfe6f5"/>`,
      extra: `<path d="M21 46c4 2 18 2 22 0" fill="none" stroke="#5f97c4" stroke-width="2.2" stroke-linecap="round"/>
              ${holding('#5f97c4', 'white')}`,
    }),
  },
  {
    key: 'lynx',
    label: 'Lynx',
    ball: 'white',
    svg: mascot({
      fur: '#cbb79a',
      ears: `<path d="M14 26l3-14 11 8z" fill="#ab9678"/><path d="M50 26l-3-14-11 8z" fill="#ab9678"/>
             <path d="M16 13l1-7M48 13l-1-7" stroke="#ab9678" stroke-width="2.6" stroke-linecap="round"/>`,
      muzzle: `<ellipse cx="32" cy="42" rx="9" ry="6" fill="#f0e6d6"/>`,
      extra: `<path d="M32 38l3 3h-6z" fill="${INK}"/>
              <path d="M32 41v2M28 45c2 2 6 2 8 0M28 45c-2 2-6 2-8 0" stroke="${INK}" stroke-width="2.1" fill="none" stroke-linecap="round"/>
              <path d="M13 41l7-2M13 46l7-2M51 41l-7-2M51 46l-7-2" stroke="${CHALK}" stroke-width="1.6" opacity="0.75"/>
              ${holding('#ab9678', 'white')}`,
    }),
  },
  {
    key: 'crane',
    label: 'Crane',
    ball: 'white',
    svg: mascot({
      fur: '#f7fbff',
      ears: `<path d="M24 16c0-5 4-8 8-8s8 3 8 8z" fill="#d8232a"/>`,
      eyes: 'dot',
      extra: `<path d="M32 37l14 4-14 4z" fill="#ffb020"/>
              <path d="M32 37l14 4-14 1z" fill="#e08c00"/>
              <path d="M16 44c-3 4-2 8 2 10" fill="none" stroke="#d9e6ef" stroke-width="3" stroke-linecap="round"/>
              ${holding('#d9e6ef', 'white')}`,
    }),
  },
  {
    key: 'turtle',
    label: 'Turtle',
    ball: 'lime',
    svg: mascot({
      fur: '#6fbf72',
      ears: `<path d="M9 30c0-13 10-22 23-22s23 9 23 22z" fill="#3f7d4a"/>
             <path d="M32 8v22M13 28l7-9M51 28l-7-9M22 12l3 16M42 12l-3 16" stroke="#2c5c36" stroke-width="2" fill="none"/>`,
      muzzle: `<ellipse cx="32" cy="42" rx="9" ry="6.5" fill="#9ad99c"/>`,
      extra: `<circle cx="29" cy="40" r="1.4" fill="${INK}"/><circle cx="35" cy="40" r="1.4" fill="${INK}"/>
              <path d="M26 46c4 2.5 8 2.5 12 0" stroke="${INK}" stroke-width="2.2" fill="none" stroke-linecap="round"/>
              ${holding('#3f7d4a', 'lime')}`,
    }),
  },
  {
    key: 'chameleon',
    label: 'Chameleon',
    ball: 'lime',
    svg: mascot({
      fur: '#8fd14f',
      ears: `<path d="M18 22c2-9 7-14 14-14s12 5 14 14z" fill="#66a52e"/>
             <path d="M24 12l-2-6M32 8V2M40 12l2-6" stroke="#66a52e" stroke-width="2.4" stroke-linecap="round"/>`,
      eyes: 'wide',
      muzzle: `<path d="M32 38c7 0 11 3 11 6s-5 6-11 6-11-3-11-6 4-6 11-6z" fill="#b6e87e"/>`,
      extra: `<path d="M23 46c5 2.5 13 2.5 18 0" fill="none" stroke="#4d8a1f" stroke-width="2.2" stroke-linecap="round"/>
              <path d="M12 44c-5 1-6 7-1 8 3 .5 4-2 2-3" fill="none" stroke="#66a52e" stroke-width="3" stroke-linecap="round"/>
              ${holding('#66a52e', 'lime')}`,
    }),
  },
  {
    key: 'crocodile',
    label: 'Crocodile',
    ball: 'lime',
    svg: mascot({
      fur: '#5fa05f',
      ears: `<circle cx="21" cy="19" r="5" fill="#478047"/><circle cx="43" cy="19" r="5" fill="#478047"/>
             <circle cx="21" cy="19" r="2.2" fill="${INK}"/><circle cx="43" cy="19" r="2.2" fill="${INK}"/>`,
      eyes: 'squint',
      muzzle: `<path d="M18 38h28c0 7-6 11-14 11s-14-4-14-11z" fill="#7cbd7c"/>`,
      extra: `<path d="M20 40l3 4 3-4 3 4 3-4 3 4 3-4 3 4 3-4" fill="none" stroke="${CHALK}" stroke-width="1.8"/>
              <path d="M14 30l6-3M50 30l-6-3" stroke="#478047" stroke-width="2.4" stroke-linecap="round"/>
              ${holding('#478047', 'lime')}`,
    }),
  },
  {
    key: 'parrot',
    label: 'Parrot',
    ball: 'lime',
    svg: mascot({
      fur: '#4aa3ff',
      ears: `<path d="M20 20c1-8 6-13 12-13s11 5 12 13z" fill="#ffd24a"/>
             <path d="M26 9l-3-6M32 7V1M38 9l3-6" stroke="#ffd24a" stroke-width="2.4" stroke-linecap="round"/>`,
      eyes: 'dot',
      extra: `<circle cx="25" cy="31" r="4.6" fill="${CHALK}"/><circle cx="39" cy="31" r="4.6" fill="${CHALK}"/>
              <circle cx="25.6" cy="31.4" r="2.3" fill="${INK}"/><circle cx="38.4" cy="31.4" r="2.3" fill="${INK}"/>
              <path d="M32 37c5 0 8 3 8 6s-4 7-8 7c3-3 3-9 0-13z" fill="#ff8c3a"/>
              <path d="M32 37c-5 0-8 3-8 6s4 7 8 7c-3-3-3-9 0-13z" fill="#e8701c"/>
              ${holding('#2b7fd4', 'lime')}`,
    }),
  },
]

/* ── The nine ────────────────────────────────────────────────────────────────
 *
 * A themed block: the animals a basketball league is named after. Two of them
 * arrived with names the collection already used, which is why the founding
 * bull is now the Ox and the second set's hawk is now the Falcon — the
 * drawings are untouched, and a picker cannot list two animals called Bull.
 *
 * Each one holds a ball, so the liveries stay four-to-a-colour where they can
 * and no group is left with a single member.
 */
const THE_NINE: Mark[] = [
  {
    key: 'hawk',
    label: 'Hawk',
    ball: 'orange',
    svg: mascot({
      fur: '#a85a2c',
      ears: `<path d="M32 12c-12 0-20 7-21 16 6-5 12-7 21-7s15 2 21 7c-1-9-9-16-21-16z" fill="#7e3a17"/>`,
      /* The cream face mask is the whole difference between this bird and the
         Falcon: a hawk's eyes sit in a pale mask, a falcon's in dark feathers. */
      muzzle: `<path d="M22 30c0-4 4-7 10-7s10 3 10 7c0 9-4 17-10 17s-10-8-10-17z" fill="#f2e3cf"/>`,
      eyes: 'dot',
      extra: `<path d="M19 26l8 3M45 26l-8 3" stroke="#5e2a10" stroke-width="3" stroke-linecap="round"/>
              <path d="M28.8 35h6.4l-1.3 7.4c-.3 1.9.7 3 2.1 3.6-2 1.6-4.6.7-5.1-1.8z" fill="#ffc94d"/>
              ${holding('#7e3a17', 'orange')}`,
    }),
  },
  {
    key: 'hornet',
    label: 'Hornet',
    ball: 'lime',
    svg: mascot({
      fur: '#f6b912',
      ears: `<path d="M23 15c-4-6-9-8-13-6" fill="none" stroke="${INK}" stroke-width="2.4" stroke-linecap="round"/>
             <circle cx="9" cy="8" r="2.8" fill="${INK}"/>
             <path d="M41 15c4-6 9-8 13-6" fill="none" stroke="${INK}" stroke-width="2.4" stroke-linecap="round"/>
             <circle cx="55" cy="8" r="2.8" fill="${INK}"/>`,
      eyes: 'wide',
      /* Two bands, not a black jaw. A dark mass across the mouth reads as a
         muzzle strap at 40px; stripes read as an insect at every size. */
      extra: `<path d="M14 39h36" stroke="#1f1f24" stroke-width="5" stroke-linecap="round"/>
              <path d="M20 47h24" stroke="#1f1f24" stroke-width="5" stroke-linecap="round"/>
              <path d="M27 51l-2.5 3M37 51l2.5 3" stroke="#1f1f24" stroke-width="2.4" stroke-linecap="round" fill="none"/>
              ${holding('#c98f06', 'lime')}`,
    }),
  },
  {
    key: 'bull',
    label: 'Bull',
    ball: 'orange',
    svg: mascot({
      fur: '#33383f',
      ears: `<path d="M21 31C9 31 4 23 6 14M43 31c12 0 17-8 15-17" fill="none" stroke="#eef2f5" stroke-width="5.5" stroke-linecap="round"/>
             <ellipse cx="13" cy="37" rx="5" ry="3.4" fill="#22262b"/><ellipse cx="51" cy="37" rx="5" ry="3.4" fill="#22262b"/>`,
      muzzle: `<ellipse cx="32" cy="43" rx="10" ry="7.5" fill="#b08a86"/>`,
      eyes: 'squint',
      extra: `<ellipse cx="28" cy="41.5" rx="2.2" ry="2.8" fill="${INK}"/><ellipse cx="36" cy="41.5" rx="2.2" ry="2.8" fill="${INK}"/>
              <circle cx="32" cy="50" r="3" fill="none" stroke="#c9a227" stroke-width="1.7"/>
              ${holding('#22262b', 'orange')}`,
    }),
  },
  {
    key: 'horse',
    label: 'Horse',
    ball: 'white',
    svg: mascot({
      fur: '#a4643a',
      ears: `<path d="M17 22l1-12 9 9z" fill="#83492a"/><path d="M47 22l-1-12-9 9z" fill="#83492a"/>
             <path d="M26 16c2-8 10-8 12 0 2-5 5-3 5 2l-3 8H24l-3-8c0-5 3-7 5-2z" fill="#2e2a28"/>`,
      muzzle: `<ellipse cx="32" cy="45" rx="8.5" ry="9" fill="#c9885a"/>`,
      extra: `<path d="M30.6 19h2.8l1.6 17c.3 2.4-5 2.4-4.7 0z" fill="#f0e6dc"/>
              <ellipse cx="29" cy="46" rx="1.8" ry="2.6" fill="${INK}"/><ellipse cx="35" cy="46" rx="1.8" ry="2.6" fill="${INK}"/>
              <path d="M28 51c2.5 1.6 5.5 1.6 8 0" stroke="${INK}" stroke-width="2" fill="none" stroke-linecap="round"/>
              ${holding('#83492a', 'white')}`,
    }),
  },
  {
    key: 'grizzly',
    label: 'Grizzly bear',
    ball: 'orange',
    svg: mascot({
      fur: '#6f4a2c',
      ears: `<circle cx="15" cy="22" r="6" fill="#54371f"/><circle cx="49" cy="22" r="6" fill="#54371f"/>`,
      muzzle: `<path d="M32 36c8 0 12 4 12 8s-5 8-12 8-12-3-12-8 4-8 12-8z" fill="#9c7350"/>`,
      eyes: 'squint',
      /* Everything that separates this from the founding Bear is in the jaw:
         darker fur, a wider snout, a brow, and two teeth showing. */
      extra: `<path d="M19 27l7-4M45 27l-7-4" stroke="#54371f" stroke-width="2.6" stroke-linecap="round"/>
              <ellipse cx="32" cy="39" rx="4" ry="3" fill="${INK}"/>
              <path d="M32 42v2.5M26 46c4 3 8 3 12 0" stroke="${INK}" stroke-width="2.3" fill="none" stroke-linecap="round"/>
              <path d="M28 46l1.5 3.5M36 46l-1.5 3.5" stroke="${CHALK}" stroke-width="2" stroke-linecap="round" fill="none"/>
              ${holding('#54371f', 'orange')}`,
    }),
  },
  {
    key: 'deer',
    label: 'Deer',
    ball: 'aba',
    svg: mascot({
      fur: '#c08b53',
      ears: `<path d="M22 23c-3-7-3-12-5-15M17 8l-5 2M18 13l-6-1M20 18l-5 1" fill="none" stroke="#8a6b4a" stroke-width="2.6" stroke-linecap="round"/>
             <path d="M42 23c3-7 3-12 5-15M47 8l5 2M46 13l6-1M44 18l5 1" fill="none" stroke="#8a6b4a" stroke-width="2.6" stroke-linecap="round"/>
             <ellipse cx="13" cy="31" rx="6" ry="3.6" fill="#a06f3c" transform="rotate(-20 13 31)"/>
             <ellipse cx="51" cy="31" rx="6" ry="3.6" fill="#a06f3c" transform="rotate(20 51 31)"/>`,
      muzzle: `<ellipse cx="32" cy="44" rx="7.5" ry="6" fill="#e3c39c"/>`,
      extra: `<ellipse cx="32" cy="41" rx="3" ry="2.4" fill="${INK}"/>
              <path d="M27 47c3.5 2 6.5 2 10 0" stroke="${INK}" stroke-width="2.1" fill="none" stroke-linecap="round"/>
              ${holding('#a06f3c', 'aba')}`,
    }),
  },
  {
    key: 'timber-wolf',
    label: 'Timber wolf',
    ball: 'white',
    svg: mascot({
      fur: '#4e5a66',
      ears: `<path d="M12 24l4-13 10 8z" fill="#3a444e"/><path d="M52 24l-4-13-10 8z" fill="#3a444e"/>`,
      muzzle: `<path d="M32 35c7 0 12 5 12 9s-5 8-12 8-12-4-12-8 5-9 12-9z" fill="#e8ddcb"/>`,
      eyes: 'dot',
      extra: `<path d="M17 30c3-5 9-6 15-6s12 1 15 6c-3 6-8 8-15 8s-12-2-15-8z" fill="#e8ddcb"/>
              <circle cx="25" cy="32" r="4.4" fill="${CHALK}"/><circle cx="39" cy="32" r="4.4" fill="${CHALK}"/>
              <circle cx="25" cy="32.2" r="2.2" fill="#ffb020"/><circle cx="39" cy="32.2" r="2.2" fill="#ffb020"/>
              <path d="M19 26l7 2M45 26l-7 2" stroke="#3a444e" stroke-width="2.6" stroke-linecap="round"/>
              <path d="M32 38l3.2 3h-6.4z" fill="${INK}"/>
              <path d="M32 41v3M27 46c3 2.4 7 2.4 10 0" stroke="${INK}" stroke-width="2.1" fill="none" stroke-linecap="round"/>
              ${holding('#3a444e', 'white')}`,
    }),
  },
  {
    key: 'pelican',
    label: 'Pelican',
    ball: 'aba',
    svg: mascot({
      fur: '#f2f4f6',
      ears: `<path d="M32 9c-4 2-6 6-6 10h12c0-4-2-8-6-10z" fill="#dfe6ea"/>`,
      /* The bill is the bird. It is drawn as two pieces — a flat upper
         mandible wider than the head's chin, and a pouch hanging under it —
         because one shape at this size reads as a paper envelope. */
      extra: `<path d="M20 36h24l-1 3.6H21z" fill="#e8a000"/>
              <path d="M23 39.6h18l-1.2 8c-1.4 6.5-14.2 6.5-15.6 0z" fill="#ffc94d"/>
              ${holding('#dfe6ea', 'aba')}`,
    }),
  },
  {
    key: 'raptor',
    label: 'Raptor',
    ball: 'lime',
    svg: mascot({
      fur: '#2f8f7f',
      ears: `<path d="M19 20l-3-7 6 2 1-6 4 5 5-6 5 6 4-5 1 6 6-2-3 7z" fill="#1f6b5e"/>`,
      muzzle: `<path d="M19 36h26c0 8-6 13-13 13s-13-5-13-13z" fill="#3fa896"/>`,
      eyes: 'dot',
      extra: `<circle cx="25" cy="31" r="4.4" fill="#ffd24a"/><circle cx="39" cy="31" r="4.4" fill="#ffd24a"/>
              <ellipse cx="25" cy="31" rx="1.3" ry="3.4" fill="${INK}"/><ellipse cx="39" cy="31" rx="1.3" ry="3.4" fill="${INK}"/>
              <path d="M19 25l7 2M45 25l-7 2" stroke="#1f6b5e" stroke-width="2.6" stroke-linecap="round"/>
              <path d="M20 41h24v1c0 6-5 10-12 10s-12-4-12-10z" fill="${INK}"/>
              <path d="M23 41l2 4.5 2-4.5zM31 41l2 4.5 2-4.5zM39 41l2 4.5 2-4.5z" fill="${CHALK}"/>
              ${holding('#1f6b5e', 'lime')}`,
    }),
  },
]

/** Every mark, in picker order: founders, then ballers, then the nine. */
export const MARKS: Mark[] = [...FOUNDERS, ...BALLERS, ...THE_NINE]

/** Key → mark, for resolving what the backend stored. */
const BY_KEY = new Map(MARKS.map((mark) => [mark.key, mark]))

/**
 * The mark a stored key names, or `null`.
 *
 * `null` for an unknown key is deliberate and the caller must handle it: an
 * older client that has just been served a newer player row is the ordinary
 * case, and it should fall back to initials rather than to a hole.
 */
export function getMark(key: string | null | undefined): Mark | null {
  return key ? (BY_KEY.get(key) ?? null) : null
}
