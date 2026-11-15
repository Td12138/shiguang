import type { ReactNode } from 'react';
import styles from './EmptyState.module.css';

export interface EmptyStateProps {
  title: string;
  description?: string;
  /** 主行动按钮 / 链接 */
  action?: ReactNode;
  /** 自定义图形，缺省用叶子图标 */
  icon?: ReactNode;
  tone?: 'default' | 'inline';
}

function LeafIcon() {
  return (
    <svg viewBox="0 0 48 48" width="40" height="40" fill="none" aria-hidden="true" focusable="false">
      <path
        d="M12 36c0-12 8-20 24-22-1 16-9 24-22 24"
        stroke="currentColor"
        strokeWidth="2.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path d="M12 36c4-8 10-14 18-17" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" />
    </svg>
  );
}

/** 体面空态：不写 TODO，只说明「现在没有什么 + 下一步能做什么」 */
export function EmptyState({ title, description, action, icon, tone = 'default' }: EmptyStateProps) {
  return (
    <div className={styles.wrap} data-tone={tone}>
      <span className={styles.icon} aria-hidden="true">
        {icon ?? <LeafIcon />}
      </span>
      <h3 className={styles.title}>{title}</h3>
      {description ? <p className={styles.description}>{description}</p> : null}
      {action ? <div className={styles.action}>{action}</div> : null}
    </div>
  );
}
