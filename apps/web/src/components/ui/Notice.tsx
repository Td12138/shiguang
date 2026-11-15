import type { ReactNode } from 'react';
import styles from './Notice.module.css';

export type NoticeTone = 'info' | 'warn' | 'error';

export interface NoticeProps {
  tone?: NoticeTone;
  title?: string;
  children?: ReactNode;
  /** 右侧动作（重试、关闭） */
  action?: ReactNode;
}

const TONE_ICON: Record<NoticeTone, string> = {
  info: 'i',
  warn: '!',
  error: '!',
};

/** 提示条：warnings / 降级 / 错误统一用它，错误自动 role=alert */
export function Notice({ tone = 'info', title, children, action }: NoticeProps) {
  return (
    <div className={styles.notice} data-tone={tone} role={tone === 'error' ? 'alert' : 'status'}>
      <span className={styles.badge} aria-hidden="true">
        {TONE_ICON[tone]}
      </span>
      <div className={styles.body}>
        {title ? <strong className={styles.title}>{title}</strong> : null}
        {children ? <div className={styles.text}>{children}</div> : null}
      </div>
      {action ? <div className={styles.action}>{action}</div> : null}
    </div>
  );
}
