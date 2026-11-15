import type { ReactNode } from 'react';
import type { ReconcileAdded, ReconcileReduced, ReconcileSuspect } from '@/lib/api';
import { CollapseGroup } from '@/components/ui/CollapseGroup';
import { ConfidenceBar } from '@/components/ui/ConfidenceBar';
import { formatQty } from '@/lib/format';
import { QTY_MIN, QTY_STEP } from '@/lib/qty';
import styles from './ReconcileGroups.module.css';

export interface ReconcileReducedGroupProps {
  items: ReconcileReduced[];
  values: Record<string, string>;
  onChange: (id: string, value: string) => void;
  /** 行内错误：inventory_id → 文案 */
  errors?: Record<string, string>;
  disabled?: boolean;
}

/** 变少了：显示 从 6 → 2，数量可改，默认按识别值 */
export function ReconcileReducedGroup({
  items,
  values,
  onChange,
  errors = {},
  disabled = false,
}: ReconcileReducedGroupProps) {
  if (items.length === 0) return null;

  return (
    <CollapseGroup title="变少了" count={items.length} hint="默认按识别出的数量更新，支持 0.5">
      <ul className={styles.list}>
        {items.map((item) => (
          <li key={item.inventory_id} className={styles.row}>
            <div className={styles.info}>
              <strong className={styles.name}>{item.name}</strong>
            </div>
            <div className={styles.flow}>
              <span>从 {formatQty(item.from_qty, item.unit)}</span>
              <span className={styles.arrow} aria-hidden="true">
                →
              </span>
              <input
                className={styles.qtyInput}
                type="number"
                inputMode="decimal"
                min={QTY_MIN}
                step={QTY_STEP}
                value={values[item.inventory_id] ?? `${item.to_qty}`}
                onChange={(event) => onChange(item.inventory_id, event.target.value)}
                aria-label={`${item.name} 实际剩余数量`}
                aria-invalid={Boolean(errors[item.inventory_id]) || undefined}
                disabled={disabled}
              />
              <span>{item.unit}</span>
              {errors[item.inventory_id] ? (
                <span className={styles.error} role="alert">
                  {errors[item.inventory_id]}
                </span>
              ) : values[item.inventory_id] === `${item.from_qty}` ? (
                <span className={styles.unchanged}>未变化，不会提交</span>
              ) : null}
            </div>
          </li>
        ))}
      </ul>
    </CollapseGroup>
  );
}

export interface ReconcileAddedGroupProps {
  items: ReconcileAdded[];
  picked: Record<string, boolean>;
  onToggle: (name: string) => void;
  disabled?: boolean;
  /** 组内附加内容：对账允许在「新增」里手动补，其它组不放 */
  children?: ReactNode;
}

/** 新增：默认不勾选，勾了才入库；组内可手动加 */
export function ReconcileAddedGroup({
  items,
  picked,
  onToggle,
  disabled = false,
  children,
}: ReconcileAddedGroupProps) {
  if (items.length === 0 && !children) return null;

  return (
    <CollapseGroup title="新增" count={items.length} hint="勾选后才会入库，也可手输">
      <ul className={styles.list}>
        {items.map((item) => {
          const checked = picked[item.name] === true;
          return (
            <li key={item.name}>
              <label className={styles.addedRow} data-picked={checked || undefined}>
                <input
                  className={styles.check}
                  type="checkbox"
                  checked={checked}
                  onChange={() => onToggle(item.name)}
                  disabled={disabled}
                  aria-label={`入库新增食材：${item.name}`}
                />
                <span className={styles.addedMain}>
                  <span className={styles.addedName}>
                    <strong className={styles.name}>{item.name}</strong>
                    <span className={styles.meta}>{formatQty(item.qty, item.unit)}</span>
                  </span>
                  <span className={styles.tags}>
                    {item.matched ? null : <span className={styles.tag} data-warn>未匹配食材库</span>}
                    {item.confidence < 0.7 ? (
                      <span className={styles.tag} data-warn>
                        置信度偏低
                      </span>
                    ) : null}
                  </span>
                </span>
                <span className={styles.confidence}>
                  <ConfidenceBar value={item.confidence} compact />
                </span>
              </label>
            </li>
          );
        })}
      </ul>
      {children}
    </CollapseGroup>
  );
}

export interface ReconcileSuspectGroupProps {
  items: ReconcileSuspect[];
}

/** 看不清：只提示，不可操作 */
export function ReconcileSuspectGroup({ items }: ReconcileSuspectGroupProps) {
  if (items.length === 0) return null;

  return (
    <CollapseGroup
      title="看不清"
      count={items.length}
      hint="仅提示，不作为判定"
      defaultOpen={false}
      tone="default"
    >
      <ul className={styles.list}>
        {items.map((item) => (
          <li key={item.inventory_id} className={styles.suspectRow}>
            <strong className={styles.name}>{item.name}</strong>
            <span className={styles.suspectReason}>{item.reason}</span>
          </li>
        ))}
      </ul>
    </CollapseGroup>
  );
}
