import type { MealPlan } from '@/lib/api';
import { Notice } from '@/components/ui/Notice';
import { CoverageBar } from './CoverageBar';
import { PlanDayColumn } from './PlanDayColumn';
import { ShoppingList } from './ShoppingList';
import styles from './PlanBody.module.css';

export interface PlanBodyProps {
  plan: MealPlan;
  inventoryTotal: number;
}

/** 计划正文：覆盖率 → 提示 → 按天分栏 + 采购清单 */
export function PlanBody({ plan, inventoryTotal }: PlanBodyProps) {
  return (
    <>
      <CoverageBar coverage={plan.coverage} inventoryTotal={inventoryTotal} />

      {plan.warnings.length > 0 ? (
        <Notice tone="warn" title="计划提示">
          <ul className={styles.warnings}>
            {plan.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </Notice>
      ) : null}

      <div className={styles.layout}>
        <div className={styles.days}>
          {plan.days.map((day, index) => (
            <PlanDayColumn key={day.date} day={day} index={index} />
          ))}
        </div>
        <ShoppingList items={plan.shopping} />
      </div>
    </>
  );
}
