import { useId } from 'react';
import { FOOD_LIST_ID, UNIT_OPTIONS } from '@/lib/foods';
import { QTY_MIN, QTY_STEP } from '@/lib/qty';
import { formatQty } from '@/lib/format';
import type { ManualDraft } from './manualRows';
import { isExternalFood } from './manualRows';
import styles from './ManualItemRow.module.css';

export interface ManualItemRowProps {
  draft: ManualDraft;
  error: string | null;
  onChange: (key: string, patch: Partial<ManualDraft>) => void;
  onRemove: (key: string) => void;
  disabled?: boolean;
}

/** 手动录入一行：名称（datalist 补全）/ 数量（0.5 步进）/ 单位 / 可选到期日 */
export function ManualItemRow({ draft, error, onChange, onRemove, disabled = false }: ManualItemRowProps) {
  const id = useId();
  const external = isExternalFood(draft.name);

  return (
    <li className={styles.row} data-error={error ? 'true' : undefined}>
      <div className={styles.fields}>
        <div className={styles.field}>
          <label className={styles.label} htmlFor={`${id}-name`}>
            名称
          </label>
          <input
            id={`${id}-name`}
            className={styles.input}
            value={draft.name}
            onChange={(event) => onChange(draft.key, { name: event.target.value })}
            list={FOOD_LIST_ID}
            placeholder="例如：西兰花"
            autoComplete="off"
            maxLength={20}
            disabled={disabled}
          />
        </div>

        <div className={styles.field}>
          <label className={styles.label} htmlFor={`${id}-qty`}>
            数量
          </label>
          <input
            id={`${id}-qty`}
            className={styles.input}
            type="number"
            inputMode="decimal"
            step={QTY_STEP}
            min={QTY_MIN}
            value={draft.qty}
            onChange={(event) => onChange(draft.key, { qty: event.target.value })}
            disabled={disabled}
            aria-invalid={Boolean(error) || undefined}
          />
        </div>

        <div className={styles.field}>
          <label className={styles.label} htmlFor={`${id}-unit`}>
            单位
          </label>
          <select
            id={`${id}-unit`}
            className={styles.input}
            value={draft.unit}
            onChange={(event) => onChange(draft.key, { unit: event.target.value })}
            disabled={disabled}
          >
            {UNIT_OPTIONS.map((unit) => (
              <option key={unit} value={unit}>
                {unit}
              </option>
            ))}
          </select>
        </div>

        <div className={styles.field}>
          <label className={styles.label} htmlFor={`${id}-expiry`}>
            到期日（可选）
          </label>
          <input
            id={`${id}-expiry`}
            className={styles.input}
            type="date"
            value={draft.expiresAt}
            onChange={(event) => onChange(draft.key, { expiresAt: event.target.value })}
            disabled={disabled}
          />
        </div>

        <button
          type="button"
          className={styles.remove}
          onClick={() => onRemove(draft.key)}
          disabled={disabled}
          aria-label={`移除手动录入行：${draft.name || '未命名'}`}
        >
          移除
        </button>
      </div>

      <div className={styles.meta}>
        <span className={styles.preview}>
          {draft.name.trim() || '未命名'} · {formatQty(Number.parseFloat(draft.qty), draft.unit)}
        </span>
        {external ? <span className={styles.tag}>库外食材，不计碳账</span> : null}
        {error ? (
          <span className={styles.error} role="alert">
            {error}
          </span>
        ) : null}
      </div>
    </li>
  );
}
