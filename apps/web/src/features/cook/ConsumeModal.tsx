import { useEffect, useState } from 'react';
import type { InventoryItem, RecipeRecommendation } from '@/lib/api';
import { Button } from '@/components/ui/Button';
import { Modal } from '@/components/ui/Modal';
import { expiryText } from '@/lib/format';
import styles from './ConsumeModal.module.css';

export interface ConsumeModalProps {
  recipe: RecipeRecommendation | null;
  inventory: InventoryItem[];
  onClose: () => void;
  onConfirm: (ids: string[]) => void;
  submitting?: boolean;
}

/** 菜名/理由里出现过的食材默认勾上，用户再确认——服务端没返回 uses 时靠这一步对齐 */
function guessUsed(recipe: RecipeRecommendation, inventory: InventoryItem[]): string[] {
  const text = `${recipe.title} ${recipe.reason}`;
  return inventory.filter((item) => text.includes(item.name)).map((item) => item.id);
}

export function ConsumeModal({
  recipe,
  inventory,
  onClose,
  onConfirm,
  submitting = false,
}: ConsumeModalProps) {
  const [checked, setChecked] = useState<string[]>([]);

  useEffect(() => {
    if (!recipe) return;
    setChecked(guessUsed(recipe, inventory));
  }, [recipe, inventory]);

  if (!recipe) return null;

  const toggle = (id: string): void => {
    setChecked((previous) =>
      previous.includes(id) ? previous.filter((item) => item !== id) : [...previous, id],
    );
  };

  return (
    <Modal
      open
      title={`「${recipe.title}」用掉了哪些食材？`}
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={onClose} disabled={submitting}>
            取消
          </Button>
          <Button
            size="sm"
            onClick={() => onConfirm(checked)}
            loading={submitting}
            disabled={checked.length === 0}
          >
            确认扣减 {checked.length} 条
          </Button>
        </>
      }
    >
      <p className={styles.hint}>
        选中的库存会整条记为「吃掉」；服务端按克数口径记碳与省钱，口径可在浪费账本核对。
      </p>
      {inventory.length === 0 ? (
        <p className={styles.empty}>冰箱里没有可扣减的库存。</p>
      ) : (
        <ul className={styles.list}>
          {inventory.map((item) => (
            <li key={item.id}>
              <label className={styles.row}>
                <input
                  type="checkbox"
                  checked={checked.includes(item.id)}
                  onChange={() => toggle(item.id)}
                />
                <span className={styles.name}>{item.name}</span>
                <span className={styles.meta}>
                  {item.qty}
                  {item.unit} · {expiryText(item.days_left)}
                </span>
              </label>
            </li>
          ))}
        </ul>
      )}
    </Modal>
  );
}
