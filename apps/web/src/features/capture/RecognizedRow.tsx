import { useId } from 'react';
import { ConfidenceBar } from '@/components/ui/ConfidenceBar';
import { QTY_MIN, QTY_STEP } from '@/lib/qty';
import type { DraftRow } from './captureRows';
import styles from './RecognizedRow.module.css';

/** 与服务端 LOW_CONFIDENCE 一致 */
const LOW_CONFIDENCE = 0.7;

export interface RecognizedRowProps {
  row: DraftRow;
  onChange: (key: string, patch: Partial<DraftRow>) => void;
  onToggle: (key: string) => void;
  /** 数量非法时的行内错误 */
  error?: string | null;
  disabled?: boolean;
}

/** 识别结果逐条校对：名称/数量/单位/到期日可改，低置信度与未匹配标黄 */
export function RecognizedRow({
  row,
  onChange,
  onToggle,
  error = null,
  disabled = false,
}: RecognizedRowProps) {
  const id = useId();
  const lowConfidence = row.confidence < LOW_CONFIDENCE;
  const flagged = lowConfidence || !row.matched;

  return (
    <li className={styles.row} data-flagged={flagged || undefined} data-muted={!row.included || undefined}>
      <div className={styles.check}>
        <input
          id={`${id}-include`}
          type="checkbox"
          checked={row.included}
          onChange={() => onToggle(row.key)}
          disabled={disabled}
          aria-label={`纳入入库：${row.name}`}
        />
      </div>

      <div className={styles.fields}>
        <div className={styles.nameField}>
          <label className={styles.label} htmlFor={`${id}-name`}>
            名称
          </label>
          <input
            id={`${id}-name`}
            className={styles.input}
            value={row.name}
            onChange={(event) => onChange(row.key, { name: event.target.value })}
            disabled={disabled}
            maxLength={24}
          />
        </div>

        <div className={styles.qtyField}>
          <label className={styles.label} htmlFor={`${id}-qty`}>
            数量
          </label>
          <input
            id={`${id}-qty`}
            className={styles.input}
            type="number"
            inputMode="decimal"
            min={QTY_MIN}
            step={QTY_STEP}
            value={row.qty}
            onChange={(event) => onChange(row.key, { qty: event.target.value })}
            disabled={disabled}
            aria-invalid={Boolean(error) || undefined}
            aria-describedby={error ? `${id}-qty-error` : undefined}
          />
          {error ? (
            <span id={`${id}-qty-error`} className={styles.qtyError} role="alert">
              {error}
            </span>
          ) : null}
        </div>

        <div className={styles.unitField}>
          <label className={styles.label} htmlFor={`${id}-unit`}>
            单位
          </label>
          <input
            id={`${id}-unit`}
            className={styles.input}
            value={row.unit}
            onChange={(event) => onChange(row.key, { unit: event.target.value })}
            disabled={disabled}
            maxLength={6}
          />
        </div>

        <div className={styles.dateField}>
          <label className={styles.label} htmlFor={`${id}-date`}>
            到期日
          </label>
          <input
            id={`${id}-date`}
            className={styles.input}
            type="date"
            value={row.expiresAt}
            onChange={(event) => onChange(row.key, { expiresAt: event.target.value })}
            disabled={disabled}
          />
        </div>

        <div className={styles.confidence}>
          <ConfidenceBar value={row.confidence} compact />
        </div>

        {flagged ? (
          <p className={styles.flags}>
            {!row.matched ? <span>未匹配食材库（不计入碳账）</span> : null}
            {lowConfidence ? <span>置信度偏低，请人工确认</span> : null}
          </p>
        ) : null}
      </div>
    </li>
  );
}
