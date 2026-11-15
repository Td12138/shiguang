import type { ReactNode } from 'react';
import type { RecipeRecommendation } from '@/lib/api';
import { CitationChip } from './CitationChip';
import { ConfidenceBar } from './ConfidenceBar';
import styles from './RecipeCard.module.css';

export interface RecipeCardProps {
  recommendation: RecipeRecommendation;
  /** 序号从 1 开始；不传则不显示 */
  index?: number;
  /** 底部操作区（做了 / 收起等） */
  actions?: ReactNode;
  /** 高亮为「首选」 */
  highlight?: boolean;
  /** 是否显示匹配度条 */
  showScore?: boolean;
}

/** 推荐卡片：菜名 / 耗时 / 理由 + 引用角标 / 缺料（必买与可选分开）/ 匹配度 */
export function RecipeCard({
  recommendation,
  index,
  actions,
  highlight = false,
  showScore = true,
}: RecipeCardProps) {
  const required = recommendation.missing.filter((item) => !item.optional);
  const optional = recommendation.missing.filter((item) => item.optional);

  return (
    <article className={styles.card} data-highlight={highlight || undefined}>
      <header className={styles.head}>
        {typeof index === 'number' ? (
          <span className={styles.rank} aria-hidden="true">
            {index}
          </span>
        ) : null}
        <h3 className={styles.title}>{recommendation.title}</h3>
        <span className={styles.minutes}>{recommendation.minutes} 分钟</span>
      </header>

      <p className={styles.reason}>
        {recommendation.reason}
        <span className={styles.citations}>
          {recommendation.citations.map((citation, citationIndex) => (
            <CitationChip
              key={`${recommendation.recipe_id}-${citation.source}-${citationIndex}`}
              citation={citation}
              index={citationIndex + 1}
            />
          ))}
        </span>
      </p>

      <div className={styles.missing}>
        <span className={styles.missingLabel}>缺料</span>
        {recommendation.missing.length === 0 ? (
          <span className={styles.allGood}>冰箱里都有</span>
        ) : (
          <ul className={styles.missingList}>
            {required.map((item) => (
              <li key={`need-${item.name}`} data-optional={undefined}>
                {item.name}
              </li>
            ))}
            {optional.map((item) => (
              <li key={`opt-${item.name}`} data-optional="true">
                {item.name}
                <span className={styles.optionalTag}>可选</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      {showScore ? <ConfidenceBar value={recommendation.score} label="匹配度" compact /> : null}
      {actions ? <div className={styles.actions}>{actions}</div> : null}
    </article>
  );
}
