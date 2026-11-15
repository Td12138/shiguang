import type { RecipeRecommendation, SuggestResponse } from '@/lib/api';
import { AgentTracePanel } from '@/components/ui/AgentTracePanel';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { Notice } from '@/components/ui/Notice';
import { RecipeCard } from '@/components/ui/RecipeCard';
import { Skeleton } from '@/components/ui/Skeleton';
import styles from './SuggestionSection.module.css';

export interface SuggestionSectionProps {
  suggestion: SuggestResponse | null;
  suggesting: boolean;
  consuming: boolean;
  doneIds: string[];
  onSuggest: () => void;
  onCooked: (recipe: RecipeRecommendation) => void;
}

/** 「② 方案」卡片：加载 / 空 / 结果 / 降级提示 / 推理过程 五态 */
export function SuggestionSection({
  suggestion,
  suggesting,
  consuming,
  doneIds,
  onSuggest,
  onCooked,
}: SuggestionSectionProps) {
  const recipes = suggestion?.recommendations ?? [];
  const warnings = suggestion?.warnings ?? [];

  return (
    <Card title="② 方案" subtitle="每条推荐都挂了引用角标，点开能看原文定位">
      {suggesting ? (
        <div className={styles.skeletons}>
          <Skeleton height="104px" radius="var(--radius-md)" />
          <Skeleton height="104px" radius="var(--radius-md)" />
        </div>
      ) : suggestion === null ? (
        <EmptyState
          tone="inline"
          title="还没有生成方案"
          description="选好食材后点「给我方案」，AI 会先看临期顺序，再检索菜谱并给出理由。"
        />
      ) : recipes.length === 0 ? (
        <EmptyState
          tone="inline"
          title="库存里没有匹配的菜谱"
          description="检索没有命中就不编造结果；可以少选几样，或放宽时间再试。"
          action={
            <Button variant="secondary" size="sm" onClick={onSuggest}>
              换一批
            </Button>
          }
        />
      ) : (
        <ol className={styles.recipes}>
          {recipes.map((recipe, index) => (
            <li key={recipe.recipe_id}>
              <RecipeCard
                recommendation={recipe}
                index={index + 1}
                highlight={index === 0}
                actions={
                  <Button
                    size="sm"
                    onClick={() => onCooked(recipe)}
                    loading={consuming}
                    disabled={doneIds.includes(recipe.recipe_id)}
                  >
                    {doneIds.includes(recipe.recipe_id) ? '已扣减库存' : '做了'}
                  </Button>
                }
              />
            </li>
          ))}
        </ol>
      )}

      {warnings.length > 0 ? (
        <Notice tone="warn" title="生成提示">
          <ul className={styles.warnings}>
            {warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </Notice>
      ) : null}

      {suggestion ? (
        <div className={styles.trace}>
          <AgentTracePanel runId={suggestion.run_id} />
        </div>
      ) : null}
    </Card>
  );
}
