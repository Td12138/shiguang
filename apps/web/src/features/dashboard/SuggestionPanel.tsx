import { useState } from 'react';
import { loadAgentRun } from '@/lib/api';
import type { AgentRun, SuggestResponse } from '@/lib/api';
import { AgentTrace } from '@/components/ui/AgentTrace';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { CitationChip } from '@/components/ui/CitationChip';
import { ConfidenceBar } from '@/components/ui/ConfidenceBar';
import { EmptyState } from '@/components/ui/EmptyState';
import { Skeleton } from '@/components/ui/Skeleton';
import { useToast } from '@/components/ui/Toast';
import styles from './SuggestionPanel.module.css';

export interface SuggestionPanelProps {
  suggestion: SuggestResponse | null;
  loading: boolean;
  onRefresh: () => void | Promise<void>;
}

/** AI 今日建议：推荐 + 理由 + 缺料 + 引用角标，可展开 Agent 步骤 */
export function SuggestionPanel({ suggestion, loading, onRefresh }: SuggestionPanelProps) {
  const { toast } = useToast();
  const [traceOpen, setTraceOpen] = useState(false);
  const [run, setRun] = useState<AgentRun | null>(null);
  const [runLoading, setRunLoading] = useState(false);
  const [runDemo, setRunDemo] = useState(false);

  const recommendations = suggestion?.recommendations ?? [];

  const handleRefresh = async (): Promise<void> => {
    await onRefresh();
    toast('已按当前库存重新计算', 'success');
  };

  const handleTrace = async (): Promise<void> => {
    if (traceOpen) {
      setTraceOpen(false);
      return;
    }
    setTraceOpen(true);
    if (run) return;
    setRunLoading(true);
    const result = await loadAgentRun(suggestion?.run_id ?? null);
    setRun(result.data);
    setRunDemo(result.demo);
    setRunLoading(false);
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
            <li
              key={rec.recipe_id}
              className={styles.item}
              data-primary={index === 0 ? 'true' : undefined}
            >
              <div className={styles.itemHead}>
                <span className={styles.rank} aria-hidden="true">
                  {index + 1}
                </span>
                <h3 className={styles.recTitle}>{rec.title}</h3>
                <span className={styles.minutes}>{rec.minutes} 分钟</span>
              </div>

              <p className={styles.reason}>
                {rec.reason}
                <span className={styles.citations}>
                  {rec.citations.map((citation, citeIndex) => (
                    <CitationChip
                      key={`${rec.recipe_id}-${citation.source}-${citeIndex}`}
                      citation={citation}
                      index={citeIndex + 1}
                    />
                  ))}
                </span>
              </p>

              <div className={styles.missingRow}>
                <span className={styles.missingLabel}>缺料</span>
                {rec.missing.length === 0 ? (
                  <span className={styles.none}>冰箱里都有</span>
                ) : (
                  <ul className={styles.missing}>
                    {rec.missing.map((ingredient) => (
                      <li key={ingredient.name} data-optional={ingredient.optional || undefined}>
                        {ingredient.name}
                        {ingredient.optional ? '（可选）' : ''}
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              <ConfidenceBar value={rec.score} label="匹配度" compact />
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

      <div className={styles.traceBlock}>
        <Button
          variant="ghost"
          size="sm"
          onClick={handleTrace}
          aria-expanded={traceOpen}
          aria-controls="agent-trace"
        >
          {traceOpen ? '收起推理过程' : '查看推理过程'}
        </Button>
        {traceOpen ? (
          <div id="agent-trace" className={styles.trace}>
            {runDemo ? <p className={styles.traceNote}>演示数据：以下步骤来自内置样例记录</p> : null}
            <AgentTrace run={run} loading={runLoading} />
          </div>
        ) : null}
      </div>
    </Card>
  );
}
