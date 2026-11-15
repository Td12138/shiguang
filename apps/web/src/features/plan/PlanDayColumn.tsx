import type { PlanDay } from '@/lib/api';
import { dayLabel } from '@/lib/format';
import { MealCard } from './MealCard';
import styles from './PlanDayColumn.module.css';

export interface PlanDayColumnProps {
  day: PlanDay;
  index: number;
}

/** 一天一栏：≥768px 并排三列，<768px 单列上下排 */
export function PlanDayColumn({ day, index }: PlanDayColumnProps) {
  return (
    <section className={styles.column} aria-label={`第 ${index + 1} 天 ${dayLabel(day.date)}`}>
      <header className={styles.head}>
        <span className={styles.index}>第 {index + 1} 天</span>
        <h3 className={styles.date}>{dayLabel(day.date)}</h3>
        <span className={styles.count}>{day.meals.length} 餐</span>
      </header>
      {day.meals.length === 0 ? (
        <p className={styles.empty}>这天没有安排，考虑搭配一道清冰箱的汤。</p>
      ) : (
        <div className={styles.meals}>
          {day.meals.map((meal) => (
            <MealCard key={`${day.date}-${meal.slot}-${meal.recipe_id}`} meal={meal} />
          ))}
        </div>
      )}
    </section>
  );
}
