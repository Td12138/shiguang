import { useId } from 'react';
import { ConfidenceBar } from '@/components/ui/ConfidenceBar';
import { formatMoney } from '@/lib/format';
import { QTY_MIN, QTY_STEP } from '@/lib/qty';
import type { ReceiptRow } from './receiptRows';
import styles from './ReceiptTable.module.css';

/** 与服务端 LOW_CONFIDENCE 一致 */
const LOW_CONFIDENCE = 0.7;

export interface ReceiptTableProps {
  rows: ReceiptRow[];
  onChange: (key: string, patch: Partial<ReceiptRow>) => void;
  onToggle: (key: string) => void;
  /** 数量非法的行：key → 行内错误 */
  errors?: Record<string, string>;
  disabled?: boolean;
}

/** 小票结果表：名称/数量/单位可改，单价与置信度只读；price 为 null 显示「—」 */
export function ReceiptTable({
  rows,
  onChange,
  onToggle,
  errors = {},
  disabled = false,
}: ReceiptTableProps) {
  const id = useId();

  return (
    <div className={styles.wrap}>
      <div className={styles.head} aria-hidden="true">
        <span />
        <span>名称</span>
        <span>数量</span>
        <span>单位</span>
        <span>单价</span>
        <span>置信度</span>
      </div>

      <ul className={styles.body}>
        {rows.map((row) => {
          const lowConfidence = row.confidence < LOW_CONFIDENCE;
          const flagged = lowConfidence || !row.matched;

          return (
            <li
              key={row.key}
              className={styles.row}
              data-flagged={flagged || undefined}
              data-muted={!row.included || undefined}
            >
              <div className={styles.check}>
                <input
                  type="checkbox"
                  checked={row.included}
                  onChange={() => onToggle(row.key)}
                  disabled={disabled}
                  aria-label={`纳入入库：${row.name}`}
                />
              </div>

              <div className={`${styles.cell} ${styles.nameCell}`}>
                <label className="visually-hidden" htmlFor={`${id}-${row.key}-name`}>
                  名称
                </label>
                <input
                  id={`${id}-${row.key}-name`}
                  className={styles.input}
                  value={row.name}
                  onChange={(event) => onChange(row.key, { name: event.target.value })}
                  disabled={disabled}
                  maxLength={24}
                />
              </div>

              <div className={`${styles.cell} ${styles.qtyCell}`}>
                <label className="visually-hidden" htmlFor={`${id}-${row.key}-qty`}>
                  数量
                </label>
                <input
                  id={`${id}-${row.key}-qty`}
                  className={styles.input}
                  type="number"
                  inputMode="decimal"
                  min={QTY_MIN}
                  step={QTY_STEP}
                  value={row.qty}
                  onChange={(event) => onChange(row.key, { qty: event.target.value })}
                  disabled={disabled}
                  aria-invalid={Boolean(errors[row.key]) || undefined}
                />
                {errors[row.key] ? (
                  <span className={styles.qtyError} role="alert">
                    {errors[row.key]}
                  </span>
                ) : null}
              </div>

              <div className={`${styles.cell} ${styles.unitCell}`}>
                <label className="visually-hidden" htmlFor={`${id}-${row.key}-unit`}>
                  单位
                </label>
                <input
                  id={`${id}-${row.key}-unit`}
                  className={styles.input}
                  value={row.unit}
                  onChange={(event) => onChange(row.key, { unit: event.target.value })}
                  disabled={disabled}
                  maxLength={6}
                />
              </div>

              <span className={styles.price} data-empty={row.price === null || undefined}>
                {formatMoney(row.price)}
              </span>

              <div className={styles.confidence}>
                <ConfidenceBar value={row.confidence} compact />
              </div>

              {flagged ? (
                <p className={styles.flags}>
                  {!row.matched ? <span>未匹配食材库（不计入碳账）</span> : null}
                  {lowConfidence ? <span>置信度偏低，请人工确认</span> : null}
                </p>
              ) : null}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
