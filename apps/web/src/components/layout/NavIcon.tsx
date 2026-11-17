import type { ReactNode } from 'react';

export type NavIconName = 'home' | 'camera' | 'calendar' | 'pot' | 'ledger' | 'report';

/** 双色填充图标：主形用 currentColor，细节用 --icon-accent，扁平圆润 */
const ACCENT = 'var(--icon-accent, #eda66a)';
const accent = { fill: ACCENT } as const;
const accentStroke = { stroke: ACCENT } as const;

const PATHS: Record<NavIconName, ReactNode> = {
  home: (
    <>
      <path
        fill="currentColor"
        d="M12 3.6 3.2 11.1a.6.6 0 0 0 .4 1.1h1.6v7.3A1.5 1.5 0 0 0 6.7 21h10.6a1.5 1.5 0 0 0 1.5-1.5v-7.3h1.6a.6.6 0 0 0 .4-1.1z"
      />
      <rect x="10" y="14" width="4" height="7" rx="1.2" style={accent} />
    </>
  ),
  camera: (
    <>
      <path fill="currentColor" d="M8.4 7 9.9 4.6a1 1 0 0 1 .9-.5h2.4a1 1 0 0 1 .9.5L15.6 7z" />
      <rect x="2.6" y="7" width="18.8" height="13" rx="3" fill="currentColor" />
      <circle cx="12" cy="13.2" r="3.6" style={accent} />
      <circle cx="18" cy="10" r="1" style={accent} />
    </>
  ),
  calendar: (
    <>
      <rect x="3.6" y="5.4" width="16.8" height="15.2" rx="3" fill="currentColor" />
      <rect x="7.6" y="3" width="2.2" height="5" rx="1.1" style={accent} />
      <rect x="14.2" y="3" width="2.2" height="5" rx="1.1" style={accent} />
      <rect x="7" y="11" width="10" height="2" rx="1" style={accent} />
      <rect x="7" y="15.4" width="6" height="2" rx="1" style={accent} />
    </>
  ),
  pot: (
    <>
      <path
        fill="currentColor"
        d="M3 10.4h18v4.1a6.5 6.5 0 0 1-6.5 6.5h-5A6.5 6.5 0 0 1 3 14.5z"
      />
      <rect x="2" y="8.2" width="20" height="2.4" rx="1.2" fill="currentColor" />
      <path
        d="M9 6.2C7.6 4.8 10.4 4 9 2.6M15 6.2c-1.4-1.4 1.4-2.2 0-3.6"
        fill="none"
        strokeWidth="1.8"
        strokeLinecap="round"
        style={accentStroke}
      />
    </>
  ),
  ledger: (
    <>
      <path
        fill="currentColor"
        d="M7.6 3H17a2 2 0 0 1 2 2v15.4a.6.6 0 0 1-.6.6H8a2.5 2.5 0 0 1-2.5-2.5v-13A2.5 2.5 0 0 1 7.6 3z"
      />
      <path d="M7.6 3a2.5 2.5 0 0 0-2.1 2.5v13A2.5 2.5 0 0 0 8 21h.6V3z" style={accent} />
      <rect x="11" y="8" width="5.6" height="1.8" rx=".9" style={accent} />
      <rect x="11" y="12" width="3.8" height="1.8" rx=".9" style={accent} />
    </>
  ),
  report: (
    <>
      <rect x="4.6" y="12.6" width="3.8" height="7.4" rx="1.4" fill="currentColor" />
      <rect x="10.1" y="7.4" width="3.8" height="12.6" rx="1.4" style={accent} />
      <rect x="15.6" y="10.2" width="3.8" height="9.8" rx="1.4" fill="currentColor" />
      <rect x="3" y="20.4" width="18" height="1.8" rx=".9" fill="currentColor" opacity=".55" />
    </>
  ),
};

export function NavIcon({ name }: { name: NavIconName }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="21"
      height="21"
      fill="none"
      stroke="none"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {PATHS[name]}
    </svg>
  );
}
