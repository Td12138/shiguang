import type { PlanCoverage } from '@/lib/api';
import styles from './CoverageBar.module.css';

export interface CoverageBarProps {
  coverage: PlanCoverage;
  /** 冰箱里现有食材总数，用来把数字说清楚 */
  inventoryTotal: number;
}

/** 计划覆盖率：用掉几样 / 救下几样临期 / 还有几样临期没用上 */
export function CoverageBar({ coverage, inventoryTotal }: CoverageBarProps) {
  const stuck = coverage.unused_expiring;

  return (
    <div className={styles.wrap} role="group" aria-label="计划覆盖率">
      <div className={styles.item}>
        <span className={styles.value}>{coverage.used_items}</span>
        <span className={styles.label}>用掉食材</span>
        <span className={styles.sub}>库存共 {inventoryTotal} 条</span>
      </div>
      <div className={styles.item} data-tone="good">
        <span className={styles.value}>{coverage.expiring_used}</span>
        <span className={styles.label}>救下临期</span>
        <span className={styles.sub}>3 天内到期的</span>
      </div>
      <div className={styles.item} data-tone={stuck > 0 ? 'warn' : undefined}>
        <span className={styles.value}>{stuck}</span>
        <span className={styles.label}>临期没用上</span>
        <span className={styles.sub}>{stuck > 0 ? '先单独处理它们' : '全都安排进去了'}</span>
      </div>
    </div>
  );
}
