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
  /** 已加入备菜的菜谱 id（最多 6 道，顺序即勾选顺序） */
  picked: string[];
  canPickMore: boolean;
  onTogglePick: (recipeId: string) => void;
  onSequence: () => void;
  sequencing: boolean;
}

/** 「② 方案」卡片：加载 / 空 / 结果 / 降级提示 / 推理过程 / 备菜选择 */
export function SuggestionSection({
  suggestion,
  suggesting,
  consuming,
  doneIds,
  onSuggest,
  onCooked,
  picked,
  canPickMore,
  onTogglePick,
  onSequence,
  sequencing,
}: SuggestionSectionProps) {
  const recipes = suggestion?.recommendations ?? [];
  const warnings = suggestion?.warnings ?? [];

  return (
    <Card
      title="② 方案"
      subtitle="每条推荐都挂了引用角标；可多选 1–6 道生成备菜时间轴"
      actions={
        recipes.length > 0 ? (
          <div className={styles.actions}>
            <span className={styles.pickCount}>已选 {picked.length}/6</span>
            <Button
              size="sm"
              onClick={onSequence}
              loading={sequencing}
              disabled={picked.length === 0 || sequencing}
            >
              开始做这几道
            </Button>
          </div>
        ) : null
      }
    >
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
        <>
          <ol className={styles.recipes}>
            {recipes.map((recipe, index) => {
              const selected = picked.includes(recipe.recipe_id);
              return (
                <li key={recipe.recipe_id}>
                  <RecipeCard
                    recommendation={recipe}
                    index={index + 1}
                    highlight={index === 0}
                    actions={
                      <>
                        <Button
                          size="sm"
                          onClick={() => onCooked(recipe)}
                          loading={consuming}
                          disabled={doneIds.includes(recipe.recipe_id)}
                        >
                          {doneIds.includes(recipe.recipe_id) ? '已扣减库存' : '做了'}
                        </Button>
                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={() => onTogglePick(recipe.recipe_id)}
                          aria-pressed={selected}
                          disabled={!selected && !canPickMore}
                        >
                          {selected ? '已加入备菜' : '加入备菜'}
                        </Button>
                      </>
                    }
                  />
                </li>
              );
            })}
          </ol>

          <p className={styles.pickHint}>
            {picked.length === 0
              ? '想让几道菜同时开火？点「加入备菜」挑 1–6 道，再点右上角「开始做这几道」。'
              : `已选 ${picked.length} 道，点右上角生成时间轴；再点一次可移出。`}
          </p>
        </>
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
