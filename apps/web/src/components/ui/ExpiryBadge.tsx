import type { ExpiryLevel } from '@/lib/api';
import { expiryText, levelText, shortDate } from '@/lib/format';
import styles from './ExpiryBadge.module.css';

export interface ExpiryBadgeProps {
  level: ExpiryLevel;
  /** 剩余天数，可为负 */
  days: number;
  /** 是否附上到期日期 */
  expiresAt?: string;
  size?: 'sm' | 'md';
}

/** 三级时效徽标：红/黄/绿由 data-level + tokens.css 统一驱动 */
export function ExpiryBadge({ level, days, expiresAt, size = 'md' }: ExpiryBadgeProps) {
  const label = `${levelText(level)}，${expiryText(days)}${expiresAt ? `，到期日 ${expiresAt}` : ''}`;

  return (
    <span className={styles.badge} data-level={level} data-size={size} aria-label={label}>
      <span className={styles.dot} aria-hidden="true" />
      <span>{expiryText(days)}</span>
      {expiresAt ? <span className={styles.date}>{shortDate(expiresAt)}</span> : null}
    </span>
  );
}
