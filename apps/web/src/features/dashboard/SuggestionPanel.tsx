import type { SuggestResponse } from '@/lib/api';
import { AgentTracePanel } from '@/components/ui/AgentTracePanel';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { RecipeCard } from '@/components/ui/RecipeCard';
import { Skeleton } from '@/components/ui/Skeleton';
import { useToast } from '@/components/ui/Toast';
import styles from './SuggestionPanel.module.css';

export interface SuggestionPanelProps {
  suggestion: SuggestResponse | null;
  loading: boolean;
  onRefresh: () => void | Promise<void>;
}

/** AI 今日建议：复用 RecipeCard，可展开 Agent 步骤 */
export function SuggestionPanel({ suggestion, loading, onRefresh }: SuggestionPanelProps) {
  const { toast } = useToast();
  const recommendations = suggestion?.recommendations ?? [];

  const handleRefresh = async (): Promise<void> => {
    await onRefresh();
    toast('已按当前库存重新计算', 'success');
  };

  return (
    <Card
      tone="accent"
      title="AI 今日建议"
      subtitle="先吃快坏的，再考虑口味"
      actions={
        <Button variant="secondary" size="sm" onClick={handleRefresh} loading={loading}>
          换一批
        </Button>
      }
    >
      {loading ? (
        <div className={styles.skeleton}>
          <Skeleton width="45%" height="22px" />
          <Skeleton lines={2} height="14px" />
          <Skeleton width="60%" height="14px" />
        </div>
      ) : recommendations.length === 0 ? (
        <EmptyState
          tone="inline"
          title="库存里没有匹配的菜谱"
          description="检索没有命中，不编造结果。可以补一条库存，或放宽时间限制再试。"
          action={
            <Button variant="secondary" size="sm" onClick={handleRefresh}>
              再试一次
            </Button>
          }
        />
      ) : (
        <ol className={styles.list}>
          {recommendations.map((rec, index) => (
            <li key={rec.recipe_id}>
              <RecipeCard recommendation={rec} index={index + 1} highlight={index === 0} />
            </li>
          ))}
        </ol>
      )}

      {suggestion?.warnings && suggestion.warnings.length > 0 ? (
        <ul className={styles.warnings}>
          {suggestion.warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      ) : null}

      <div className={styles.trace}>
        <AgentTracePanel runId={suggestion?.run_id} />
      </div>
    </Card>
  );
}
