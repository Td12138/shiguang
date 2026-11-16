import type { ReactNode } from 'react';

/** 分类小图标：扁平双色食材剪影，风格与导航图标一致 */
const ICONS: Record<string, ReactNode> = {
  蔬菜: (
    <>
      <path d="M12 2.5c6 5 8 9 8 12a8 8 0 0 1-16 0c0-3 2-7 8-12z" fill="#9DBB7D" />
      <path d="M12 8v11M12 12l3.4-3M12 15l-3.4-3" stroke="#6C8F50" strokeWidth="1.5" fill="none" strokeLinecap="round" />
    </>
  ),
  肉蛋: (
    <>
      <path d="M12 3c3.8 0 7 5.2 7 9.5a7 7 0 0 1-14 0C5 8.2 8.2 3 12 3z" fill="#EAC789" />
      <ellipse cx="9.6" cy="10.4" rx="1.7" ry="2.6" fill="#F7E7C4" transform="rotate(-18 9.6 10.4)" />
    </>
  ),
  乳制品: (
    <>
      <rect x="8" y="7" width="8" height="14" rx="2.5" fill="#C7DBD3" />
      <rect x="9.4" y="3" width="5.2" height="4.2" rx="1.4" fill="#5D8A80" />
      <path d="M8 12.5h8v4H8z" fill="#5D8A80" opacity=".4" />
    </>
  ),
  主食: (
    <>
      <path d="M6 11a6 6 0 0 1 12 0z" fill="#FBF3E4" />
      <path d="M4 11h16a8 8 0 0 1-16 0z" fill="#E4B87F" />
      <path d="M9.5 6.6v2M14.5 6.6v2M12 5.4v2" stroke="#D9C6A2" strokeWidth="1.3" strokeLinecap="round" />
    </>
  ),
  水果: (
    <>
      <circle cx="12" cy="14" r="7" fill="#E8927C" />
      <path d="M12 7.4c0-2 1-3.2 2.6-4" stroke="#8A5A3B" strokeWidth="1.8" fill="none" strokeLinecap="round" />
      <path d="M13.4 5.4c2.4-2.4 5.4-1.4 5.4-1.4s-.6 3.4-5.4 1.4z" fill="#9DBB7D" />
      <ellipse cx="9.4" cy="12" rx="1.4" ry="2.2" fill="#F6BCA6" transform="rotate(-20 9.4 12)" />
    </>
  ),
  豆制品: (
    <>
      <rect x="4" y="8" width="16" height="12" rx="2.5" fill="#F0DFB4" />
      <path d="M4 12.5h16M12 8v12" stroke="#D3B67F" strokeWidth="1.4" />
    </>
  ),
};

const FALLBACK = (
  <>
    <path d="M5 10h14l-1.6 8.6a2 2 0 0 1-2 1.4H8.6a2 2 0 0 1-2-1.4z" fill="#D8C3A3" />
    <path d="M8 10a4 4 0 0 1 8 0" stroke="#A98F66" strokeWidth="1.8" fill="none" />
  </>
);

export function CategoryIcon({ name }: { name: string }) {
  return (
    <svg viewBox="0 0 24 24" width="19" height="19" aria-hidden="true" focusable="false">
      {ICONS[name] ?? FALLBACK}
    </svg>
  );
}
