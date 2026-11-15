import { useId, useState, type ReactNode } from 'react';
import styles from './CollapseGroup.module.css';

export interface CollapseGroupProps {
  title: string;
  count: number;
  children: ReactNode;
  /** 默认展开（差异组默认展开，看不清组默认收起） */
  defaultOpen?: boolean;
  tone?: 'default' | 'warn' | 'danger';
  hint?: string;
}

/** 可折叠分组：按钮带 aria-expanded，内容区用 aria-controls 关联 */
export function CollapseGroup({
  title,
  count,
  children,
  defaultOpen = true,
  tone = 'default',
  hint,
}: CollapseGroupProps) {
  const [open, setOpen] = useState(defaultOpen);
  const bodyId = useId();

  return (
    <section className={styles.group} data-tone={tone}>
      <button
        type="button"
        className={styles.header}
        aria-expanded={open}
        aria-controls={bodyId}
        onClick={() => setOpen((previous) => !previous)}
      >
        <span className={styles.caret} aria-hidden="true">
          {open ? '▾' : '▸'}
        </span>
        <span className={styles.title}>{title}</span>
        <span className={styles.count}>{count}</span>
        {hint ? <span className={styles.hint}>{hint}</span> : null}
      </button>
      {open ? (
        <div id={bodyId} className={styles.body}>
          {children}
        </div>
      ) : null}
    </section>
  );
}
