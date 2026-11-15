import type { InventoryItem } from '@/lib/api';
import { ItemCard } from '@/components/ui/ItemCard';
import styles from './UrgentStrip.module.css';

export interface UrgentStripProps {
  /** 已按剩余天数升序排好的临期食材 */
  items: InventoryItem[];
}

/** 首页第一屏：今天必须处理。三级色条 + 剩余天数大数字，横向排列 */
export function UrgentStrip({ items }: UrgentStripProps) {
  return (
    <section className={styles.section} aria-labelledby="urgent-title">
      <header className={styles.head}>
        <div className={styles.heading}>
          <h2 id="urgent-title" className={styles.title}>
            今天必须处理
          </h2>
          <p className={styles.desc}>
            {items.length > 0
              ? `${items.length} 样食材在 3 天内到期，按这个顺序吃掉它们。`
              : '未来三天没有临期食材，冰箱状态不错。'}
          </p>
        </div>
        <ul className={styles.legend} aria-label="时效色条说明">
          <li data-level="urgent">0–1 天</li>
          <li data-level="soon">2–3 天</li>
          <li data-level="fresh">3 天以上</li>
        </ul>
      </header>

      {items.length === 0 ? (
        <p className={styles.empty}>没有需要抢在坏掉之前处理的食材，去「今日吃啥」挑一顿正常的就好。</p>
      ) : (
        <ul className={styles.row}>
          {items.map((item) => (
            <li key={item.id} className={styles.cell}>
              <ItemCard item={item} size="sm" showDays />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
