import { useCallback, useEffect, useMemo, useState } from 'react';
import type { InventoryItem, RecipeRecommendation } from '@/lib/api';
import { Button } from '@/components/ui/Button';
import { Modal } from '@/components/ui/Modal';
import { formatQty } from '@/lib/format';
import { QTY_MIN, QTY_STEP, parsePositiveQty } from '@/lib/qty';
import { gramsForQty, remainingQty, type ConsumeLine } from './consume';
import styles from './ConsumeModal.module.css';

export interface ConsumeModalProps {
  recipe: RecipeRecommendation | null;
  inventory: InventoryItem[];
  onClose: () => void;
  onConfirm: (lines: ConsumeLine[]) => void;
  submitting?: boolean;
}

/** 菜名/理由里出现过的食材默认勾上；有 uses 时只认 uses，避免把同名字的库存都勾上 */
function guessUsed(recipe: RecipeRecommendation, inventory: InventoryItem[]): string[] {
  const uses = recipe.uses ?? [];
  const ids = new Set<string>();
  uses.forEach((use) => {
    const item = use.inventory_id
      ? inventory.find((row) => row.id === use.inventory_id)
      : inventory.find((row) => row.name === use.name);
    if (item) ids.add(item.id);
  });
  if (uses.length > 0) return [...ids];
  const text = `${recipe.title} ${recipe.reason}`;
  return inventory.filter((item) => text.includes(item.name)).map((item) => item.id);
}

/** 默认数量取菜谱 uses[].qty（不能把整条库存一次扣完），没有用量时才退回整条库存 */
function defaultQty(
  item: InventoryItem,
  useById: Map<string, number>,
  useByName: Map<string, number>,
): number {
  const used = useById.get(item.id) ?? useByName.get(item.name);
  if (used === undefined || !Number.isFinite(used) || used <= 0) return item.qty;
  return Math.min(used, item.qty);
}

export function ConsumeModal({
  recipe,
  inventory,
  onClose,
  onConfirm,
  submitting = false,
}: ConsumeModalProps) {
  const [checked, setChecked] = useState<string[]>([]);
  const [qtyValues, setQtyValues] = useState<Record<string, string>>({});

  useEffect(() => {
    if (!recipe) return;
    const used = guessUsed(recipe, inventory);
    setChecked(used);
    const useById = new Map<string, number>();
    const useByName = new Map<string, number>();
    (recipe.uses ?? []).forEach((use) => {
      if (use.inventory_id) useById.set(use.inventory_id, use.qty);
      useByName.set(use.name, use.qty);
    });
    const defaults: Record<string, string> = {};
    inventory.forEach((item) => {
      defaults[item.id] = `${defaultQty(item, useById, useByName)}`;
    });
    setQtyValues(defaults);
  }, [recipe, inventory]);

  const toggle = (id: string): void => {
    setChecked((previous) =>
      previous.includes(id) ? previous.filter((item) => item !== id) : [...previous, id],
    );
  };

  const errors = useMemo(() => {
    const map: Record<string, string> = {};
    checked.forEach((id) => {
      const item = inventory.find((row) => row.id === id);
      if (!item) return;
      const raw = qtyValues[id] ?? `${item.qty}`;
      const value = parsePositiveQty(raw);
      if (value === null) map[id] = '数量要大于 0（可用 0.5）';
      else if (value > item.qty) map[id] = `不能超过库存 ${formatQty(item.qty, item.unit)}`;
    });
    return map;
  }, [checked, qtyValues, inventory]);

  const invalid = Object.keys(errors).length > 0;

  const confirm = useCallback((): void => {
    const lines: ConsumeLine[] = checked
      .map((id) => {
        const item = inventory.find((row) => row.id === id);
        if (!item) return null;
        const qty = parsePositiveQty(qtyValues[id] ?? `${item.qty}`);
        if (qty === null) return null;
        // 整条扣完就不传 grams，交给后端按剩余克数处理
        if (qty >= item.qty) return { id };
        return { id, grams: gramsForQty(item, qty) };
      })
      .filter((line): line is ConsumeLine => line !== null);
    onConfirm(lines);
  }, [checked, qtyValues, inventory, onConfirm]);

  if (!recipe) return null;

  return (
    <Modal
      open
      title={`「${recipe.title}」用掉了多少？`}
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={onClose} disabled={submitting}>
            取消
          </Button>
          <Button
            size="sm"
            onClick={confirm}
            loading={submitting}
            disabled={checked.length === 0 || invalid}
          >
            确认扣减 {checked.length} 条
          </Button>
        </>
      }
    >
      <p className={styles.hint}>
        勾选用掉的食材，可以填 0.5 这种小数；扣减按克数比例折算，剩下的仍留在库存里。
      </p>
      {inventory.length === 0 ? (
        <p className={styles.empty}>冰箱里没有可扣减的库存。</p>
      ) : (
        <ul className={styles.list}>
          {inventory.map((item) => {
            const active = checked.includes(item.id);
            const raw = qtyValues[item.id] ?? `${item.qty}`;
            const qty = parsePositiveQty(raw) ?? 0;
            const grams = active ? gramsForQty(item, qty) : undefined;
            const remaining = remainingQty(item, qty);

            return (
              <li key={item.id} className={styles.row} data-active={active || undefined}>
                <label className={styles.check}>
                  <input
                    type="checkbox"
                    checked={active}
                    onChange={() => toggle(item.id)}
                    aria-label={`勾选用掉的食材：${item.name}`}
                  />
                  <span className={styles.name}>{item.name}</span>
                  <span className={styles.stock}>库存 {formatQty(item.qty, item.unit)}</span>
                </label>

                <div className={styles.qtyRow}>
                  <input
                    className={styles.qtyInput}
                    type="number"
                    inputMode="decimal"
                    min={QTY_MIN}
                    max={item.qty}
                    step={QTY_STEP}
                    value={raw}
                    onChange={(event) =>
                      setQtyValues((previous) => ({ ...previous, [item.id]: event.target.value }))
                    }
                    disabled={!active || submitting}
                    aria-label={`${item.name} 用掉的数量`}
                    aria-invalid={Boolean(errors[item.id]) || undefined}
                  />
                  <span className={styles.unit}>{item.unit}</span>
                  {active ? (
                    <span className={styles.estimate}>
                      {errors[item.id]
                        ? errors[item.id]
                        : `${grams ? `将消耗约 ${grams} g · ` : ''}扣完剩 ${formatQty(remaining, item.unit)}`}
                    </span>
                  ) : null}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </Modal>
  );
}
