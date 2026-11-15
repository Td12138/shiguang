import type { ReactNode } from 'react';
import styles from './Card.module.css';

export interface CardProps {
  /** 有标题时渲染卡片头部；纯容器可只传 children */
  title?: ReactNode;
  subtitle?: ReactNode;
  /** 头部右侧操作区（按钮、徽标） */
  actions?: ReactNode;
  footer?: ReactNode;
  tone?: 'default' | 'soft' | 'accent';
  className?: string;
  /** 新手引导锚点 */
  dataTour?: string;
  children: ReactNode;
}

export function Card({
  title,
  subtitle,
  actions,
  footer,
  tone = 'default',
  className,
  dataTour,
  children,
}: CardProps) {
  const classes = [styles.card, className].filter(Boolean).join(' ');
  const hasHeader = Boolean(title ?? subtitle ?? actions);

  return (
    <section className={classes} data-tone={tone} data-tour={dataTour}>
      {hasHeader ? (
        <header className={styles.header}>
          <div className={styles.heading}>
            {title ? <h2 className={styles.title}>{title}</h2> : null}
            {subtitle ? <p className={styles.subtitle}>{subtitle}</p> : null}
          </div>
          {actions ? <div className={styles.actions}>{actions}</div> : null}
        </header>
      ) : null}
      <div className={styles.body}>{children}</div>
      {footer ? <footer className={styles.footer}>{footer}</footer> : null}
    </section>
  );
}
