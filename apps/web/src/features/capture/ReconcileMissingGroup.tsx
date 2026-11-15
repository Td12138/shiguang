import { DISCARD_REASON_LABELS } from '@/lib/api';
import type { DiscardReason, MissingAction, ReconcileMissing } from '@/lib/api';
import { CollapseGroup } from '@/components/ui/CollapseGroup';
import { Segmented } from '@/components/ui/Segmented';
import { expiryText, formatQty } from '@/lib/format';
import type { MissingChoice } from './useReconcile';
import styles from './ReconcileGroups.module.css';

export interface ReconcileMissingGroupProps {
  items: ReconcileMissing[];
  choices: Record<string, MissingChoice>;
  onAction: (id: string, action: MissingAction) => void;
  onReason: (id: string, reason: DiscardReason) => void;
  disabled?: boolean;
}

const ACTION_OPTIONS = [
  { value: 'keep', label: '保留' },
  { value: 'consumed', label: '吃掉了' },
  { value: 'discarded', label: '扔掉了' },
] as const;

const REASON_OPTIONS = (Object.keys(DISCARD_REASON_LABELS) as DiscardReason[]).map((reason) => ({
  value: reason,
  label: DISCARD_REASON_LABELS[reason],
}));

/** 不见了：默认 keep，任何删除都要用户亲手点 */
export function ReconcileMissingGroup({
  items,
  choices,
  onAction,
  onReason,
  disabled = false,
}: ReconcileMissingGroupProps) {
  if (items.length === 0) return null;

  return (
    <CollapseGroup
      title="不见了"
      count={items.length}
      tone="warn"
      hint="默认保留，删除必须由你确认"
    >
      <ul className={styles.list}>
        {items.map((item) => {
          const choice = choices[item.inventory_id] ?? { action: 'keep', reason: 'spoiled' };
          return (
            <li key={item.inventory_id} className={styles.row}>
              <div className={styles.info}>
                <strong className={styles.name}>{item.name}</strong>
                <span className={styles.meta}>
                  {formatQty(item.qty, item.unit)} · {expiryText(item.days_left)}
                </span>
              </div>

              <Segmented
                ariaLabel={`${item.name} 的处理方式`}
                options={ACTION_OPTIONS}
                value={choice.action}
                onChange={(action) => onAction(item.inventory_id, action)}
                disabled={disabled}
              />

              {choice.action === 'discarded' ? (
                <label className={styles.reason}>
                  丢弃原因
                  <select
                    className={styles.select}
                    value={choice.reason}
                    onChange={(event) => onReason(item.inventory_id, event.target.value as DiscardReason)}
                    aria-label={`${item.name} 丢弃原因`}
                    disabled={disabled}
                  >
                    {REASON_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </label>
              ) : null}
            </li>
          );
        })}
      </ul>
    </CollapseGroup>
  );
}
