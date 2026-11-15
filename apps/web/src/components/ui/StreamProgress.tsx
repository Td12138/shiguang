import type { AgentStep } from '@/lib/api';
import { AgentTrace } from '@/components/ui/AgentTrace';
import { Button } from '@/components/ui/Button';
import styles from './StreamProgress.module.css';

export interface StreamProgressProps {
  /** 已补齐占位的时间线 */
  steps: AgentStep[];
  delta: string;
  /** 3 秒内没有 step 事件 */
  slow: boolean;
  onCancel?: () => void;
  cancelLabel?: string;
}

/** 流式进度：时间线 + 增量文案 + 慢响应提示 + 取消；计划与推荐共用 */
export function StreamProgress({
  steps,
  delta,
  slow,
  onCancel,
  cancelLabel = '取消',
}: StreamProgressProps) {
  return (
    <div className={styles.wrap} aria-busy="true">
      <AgentTrace run={{ id: 'stream', state: 'running', steps }} showRunId={false} />

      {delta ? <p className={styles.delta}>{delta}</p> : null}

      {slow ? (
        <p className={styles.slow} role="status">
          模型响应较慢，仍在处理…
        </p>
      ) : null}

      {onCancel ? (
        <div className={styles.actions}>
          <Button variant="secondary" size="sm" onClick={onCancel}>
            {cancelLabel}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
