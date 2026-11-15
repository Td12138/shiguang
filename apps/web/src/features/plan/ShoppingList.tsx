import type { ShoppingItem } from '@/lib/api';
import styles from './ShoppingList.module.css';

export interface ShoppingListProps {
  items: ShoppingItem[];
}

/** 缺料合并后的采购清单：同一食材只出现一次（契约 §6.8 规则 5） */
export function ShoppingList({ items }: ShoppingListProps) {
  return (
    <aside className={styles.aside} aria-label="采购清单">
      <header className={styles.head}>
        <h3 className={styles.title}>采购清单</h3>
        <span className={styles.count}>{items.length} 项</span>
      </header>

      {items.length === 0 ? (
        <p className={styles.empty}>计划里的菜都能用现有库存做完，这周不用额外买。</p>
      ) : (
        <ul className={styles.list}>
          {items.map((item) => (
            <li key={item.name} className={styles.item}>
              <span className={styles.name}>{item.name}</span>
              <span className={styles.qty}>
                {item.qty}
                {item.unit}
              </span>
              <span className={styles.reason}>{item.reason}</span>
            </li>
          ))}
        </ul>
      )}
      <p className={styles.note}>缺料已按食材合并，不会重复列同一样东西。</p>
    </aside>
  );
}
