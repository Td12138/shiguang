import type { CategoryGroup } from './selectors';
import { Card } from '@/components/ui/Card';
import { ItemCard } from '@/components/ui/ItemCard';
import styles from './FridgeOverview.module.css';

export interface FridgeOverviewProps {
  groups: CategoryGroup[];
  total: number;
}

/** 冰箱全景：按类别分组的食材网格，密度低、看得清 */
export function FridgeOverview({ groups, total }: FridgeOverviewProps) {
  return (
    <Card title="冰箱全景" subtitle={`共 ${total} 件食材，按类别摆放；每张卡片左边是时效色条`}>
      <div className={styles.groups}>
        {groups.map((group) => (
          <section key={group.name} className={styles.group} aria-labelledby={`category-${group.name}`}>
            <h3 id={`category-${group.name}`} className={styles.groupTitle}>
              {group.name}
              <span className={styles.count}>{group.items.length}</span>
            </h3>
            <ul className={styles.grid}>
              {group.items.map((item) => (
                <li key={item.id}>
                  <ItemCard item={item} />
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </Card>
  );
}
