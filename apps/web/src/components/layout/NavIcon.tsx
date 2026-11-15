import type { ReactNode } from 'react';

export type NavIconName = 'home' | 'camera' | 'pot' | 'ledger' | 'report';

const PATHS: Record<NavIconName, ReactNode> = {
  home: (
    <>
      <path d="M4 10.5 12 4l8 6.5" />
      <path d="M6 9.5V19a1 1 0 0 0 1 1h3v-5h4v5h3a1 1 0 0 0 1-1V9.5" />
    </>
  ),
  camera: (
    <>
      <path d="M4 8.5h3l1.4-2h7.2L17 8.5h3a1 1 0 0 1 1 1v8a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1v-8a1 1 0 0 1 1-1Z" />
      <circle cx="12" cy="13.5" r="3.2" />
    </>
  ),
  pot: (
    <>
      <path d="M4 10h16v5a4 4 0 0 1-4 4H8a4 4 0 0 1-4-4v-5Z" />
      <path d="M2.5 10h19" />
      <path d="M9 6.5c0-1 1-1.5 1-2.5M14 6.5c0-1 1-1.5 1-2.5" />
    </>
  ),
  ledger: (
    <>
      <path d="M6 4h11a2 2 0 0 1 2 2v14H8a2 2 0 0 1-2-2V4Z" />
      <path d="M6 4a2 2 0 0 0-2 2v12" />
      <path d="M9.5 8.5h6M9.5 12h4" />
    </>
  ),
  report: (
    <>
      <path d="M4 19V5" />
      <path d="M4 19h16" />
      <path d="M8 19v-6M12.5 19V9M17 19v-4" />
    </>
  ),
};

export function NavIcon({ name }: { name: NavIconName }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="20"
      height="20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {PATHS[name]}
    </svg>
  );
}
