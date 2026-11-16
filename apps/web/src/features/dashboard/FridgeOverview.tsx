import type { InventoryItem } from '@/lib/api';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { ItemCard } from '@/components/ui/ItemCard';
import { CategoryIcon } from './CategoryIcon';
import type { CategoryGroup } from './selectors';
import styles from './FridgeOverview.module.css';

export interface FridgeOverviewProps {
  groups: CategoryGroup[];
  total: number;
  /** 有真实后端时才接编辑/丢弃；演示数据不显示写操作 */
  onEdit?: (item: InventoryItem) => void;
  onDiscard?: (item: InventoryItem) => void;
}

/** 冰箱全景：按类别分组的食材网格，密度低、看得清 */
export function FridgeOverview({ groups, total, onEdit, onDiscard }: FridgeOverviewProps) {
  return (
    <Card title="冰箱全景" subtitle={`共 ${total} 件食材，按类别摆放；每张卡片左边是时效色条`}>
      <div className={styles.groups}>
        {groups.map((group) => (
          <section key={group.name} className={styles.group} aria-labelledby={`category-${group.name}`}>
            <h3 id={`category-${group.name}`} className={styles.groupTitle}>
              <CategoryIcon name={group.name} />
              {group.name}
              <span className={styles.count}>{group.items.length}</span>
            </h3>
            <ul className={styles.grid}>
              {group.items.map((item) => (
                <li key={item.id}>
                  <ItemCard
                    item={item}
                    footer={
                      onEdit || onDiscard ? (
                        <div className={styles.cardActions}>
                          {onEdit ? (
                            <Button
                              variant="secondary"
                              size="sm"
                              onClick={() => onEdit(item)}
                              aria-label={`修改 ${item.name} 的数量或到期日`}
                            >
                              改数量/到期
                            </Button>
                          ) : null}
                          {onDiscard ? (
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => onDiscard(item)}
                              aria-label={`丢弃 ${item.name}`}
                            >
                              扔了
                            </Button>
                          ) : null}
                        </div>
                      ) : undefined
                    }
                  />
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </Card>
  );
}
