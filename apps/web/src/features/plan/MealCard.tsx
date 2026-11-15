import type { PlanMeal } from '@/lib/api';
import { CitationChip } from '@/components/ui/CitationChip';
import styles from './MealCard.module.css';

export interface MealCardProps {
  meal: PlanMeal;
}

/** 一餐：餐段 + 菜名 + 耗时 + 用掉什么 / 缺什么 / 引用 */
export function MealCard({ meal }: MealCardProps) {
  const required = meal.missing.filter((item) => !item.optional);
  const optional = meal.missing.filter((item) => item.optional);

  return (
    <article className={styles.card}>
      <header className={styles.head}>
        <span className={styles.slot}>{meal.slot}</span>
        <span className={styles.minutes}>{meal.minutes} 分钟</span>
      </header>
      <h4 className={styles.title}>{meal.title}</h4>

      {meal.uses.length > 0 ? (
        <p className={styles.uses}>
          <span className={styles.key}>用掉</span>
          {meal.uses.map((use) => (
            <span key={`${use.name}-${use.qty}`} className={styles.use}>
              {use.name}
              <em>
                {use.qty}
                {use.unit}
              </em>
            </span>
          ))}
        </p>
      ) : null}

      {meal.missing.length > 0 ? (
        <p className={styles.missing}>
          <span className={styles.key}>缺</span>
          {required.map((item) => (
            <span key={`need-${item.name}`} className={styles.need}>
              {item.name}
            </span>
          ))}
          {optional.map((item) => (
            <span key={`opt-${item.name}`} className={styles.optional}>
              {item.name}（可选）
            </span>
          ))}
        </p>
      ) : (
        <p className={styles.missing}>
          <span className={styles.key}>缺</span>
          <span className={styles.allGood}>冰箱里都有</span>
        </p>
      )}

      {meal.citations.length > 0 ? (
        <footer className={styles.foot}>
          <span className={styles.citeLabel}>引用</span>
          {meal.citations.map((citation, index) => (
            <CitationChip
              key={`${meal.recipe_id}-${citation.source}-${index}`}
              citation={citation}
              index={index + 1}
            />
          ))}
        </footer>
      ) : null}
    </article>
  );
}
