import { formatMoney } from '@/lib/format';
import styles from './ReceiptCapture.module.css';

export interface ReceiptMetaProps {
  purchasedAt: string | null;
  totalPrice: number | null;
}

/** 小票级字段：购买日期与合计（识别不出时如实说明，不补 0） */
export function ReceiptMeta({ purchasedAt, totalPrice }: ReceiptMetaProps) {
  return (
    <ul className={styles.meta}>
      <li>
        <span className={styles.metaKey}>购买日期</span>
        <strong className={styles.metaValue} data-empty={purchasedAt === null || undefined}>
          {purchasedAt ?? '小票未识别出日期'}
        </strong>
      </li>
      <li>
        <span className={styles.metaKey}>合计</span>
        <strong className={styles.metaValue} data-empty={totalPrice === null || undefined}>
          {totalPrice === null ? '小票未识别出合计' : formatMoney(totalPrice)}
        </strong>
      </li>
    </ul>
  );
}
