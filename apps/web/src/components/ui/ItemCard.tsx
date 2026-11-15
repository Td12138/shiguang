import type { ReactNode } from 'react';
import type { InventoryItem } from '@/lib/api';
import { resolveCategory } from '@/lib/categories';
import { expiryText } from '@/lib/format';
import { Button } from './Button';
import { ConfidenceBar } from './ConfidenceBar';
import { ExpiryBadge } from './ExpiryBadge';
import styles from './ItemCard.module.css';

export interface ItemCardProps {
  item: InventoryItem;
  /** sm 用于临期横排，md 用于冰箱网格 */
  size?: 'md' | 'sm';
  /** 是否把剩余天数做成大数字（临期卡片的主视觉） */
  showDays?: boolean;
  actionLabel?: string;
  onAction?: (item: InventoryItem) => void;
  /** 自定义底部内容（后续页面做勾选、扣减等操作时用） */
  footer?: ReactNode;
}

/** 食材卡片：左侧色条标时效，大数字标剩余天数，类别取自后端或本地兜底 */
export function ItemCard({
  item,
  size = 'md',
  showDays = false,
  actionLabel,
  onAction,
  footer,
}: ItemCardProps) {
  const category = resolveCategory(item);
  const ariaLabel = `${category}，${item.name}，${item.qty}${item.unit}，${expiryText(item.days_left)}`;

  return (
    <article className={styles.card} data-level={item.level} data-size={size} aria-label={ariaLabel}>
      <span className={styles.stripe} aria-hidden="true" />
      <div className={styles.inner}>
        <header className={styles.head}>
          <h3 className={styles.name}>{item.name}</h3>
          <span className={styles.category}>{category}</span>
          <span className={styles.qty}>
            {item.qty}
            {item.unit}
          </span>
        </header>

        {showDays ? (
          <p className={styles.days} data-level={item.level}>
            {item.days_left}
            <span className={styles.daysUnit}> 天</span>
          </p>
        ) : null}

        <footer className={styles.foot}>
          <ExpiryBadge
            level={item.level}
            days={item.days_left}
            expiresAt={item.expires_at}
            size="sm"
          />
          {typeof item.confidence === 'number' ? (
            <ConfidenceBar value={item.confidence} compact />
          ) : null}
        </footer>

        {footer ? <div className={styles.extra}>{footer}</div> : null}
        {onAction ? (
          <Button variant="secondary" size="sm" onClick={() => onAction(item)}>
            {actionLabel ?? '处理'}
          </Button>
        ) : null}
      </div>
    </article>
  );
}
