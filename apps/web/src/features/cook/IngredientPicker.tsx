import type { InventoryItem } from '@/lib/api';
import { Chip } from '@/components/ui/Chip';
import { expiryText } from '@/lib/format';
import styles from './IngredientPicker.module.css';

export interface IngredientPickerProps {
  inventory: InventoryItem[];
  selected: string[];
  onToggle: (id: string) => void;
  disabled?: boolean;
}

/** 临期食材多选：默认全选 3 天内到期的，chip 上标剩余天数 */
export function IngredientPicker({ inventory, selected, onToggle, disabled = false }: IngredientPickerProps) {
  return (
    <div className={styles.wrap}>
      {inventory.map((item) => (
        <Chip
          key={item.id}
          label={item.name}
          hint={`${expiryText(item.days_left)} · ${item.qty}${item.unit}`}
          selected={selected.includes(item.id)}
          onToggle={() => onToggle(item.id)}
          disabled={disabled}
        />
      ))}
    </div>
  );
}
