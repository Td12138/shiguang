import type { AgentRun, AgentStep, AgentStepStatus } from '@/lib/api';
import { Skeleton } from './Skeleton';
import styles from './AgentTrace.module.css';

/** 契约 §9 的步骤名 → 中文标签 */
const STEP_LABELS: Record<string, string> = {
  understand: '理解需求',
  plan: '规划工具调用',
  retrieve: '检索菜谱',
  compose: '组织建议',
  verify: '引用校验',
};

const STATUS_TEXT: Record<AgentStepStatus, string> = {
  ok: '完成',
  error: '失败',
  running: '进行中',
  pending: '等待',
};

function stepLabel(name: string): string {
  return STEP_LABELS[name] ?? name;
}

export interface AgentTraceProps {
  run: AgentRun | null;
  loading?: boolean;
  error?: string | null;
}

/** Agent 步骤时间线：让「规划 → 调工具 → 自检」的过程可回放（契约 §9） */
export function AgentTrace({ run, loading = false, error = null }: AgentTraceProps) {
  if (loading) {
    return (
      <div className={styles.loading}>
        <Skeleton lines={3} height="14px" />
      </div>
    );
  }

  if (error) {
    return (
      <p className={styles.error} role="alert">
        步骤记录读取失败：{error}
      </p>
    );
  }

  if (!run) {
    return <p className={styles.hint}>暂无步骤记录。</p>;
  }

  return (
    <div className={styles.wrap}>
      <div className={styles.meta}>
        <span className={styles.runId}>run · {run.id}</span>
        <span className={styles.state} data-state={run.state}>
          {run.state === 'ok' ? '全部通过' : run.state}
        </span>
      </div>
      <ol className={styles.timeline}>
        {run.steps.map((step: AgentStep, index) => (
          <li key={`${step.name}-${index}`} className={styles.step} data-status={step.status}>
            <span className={styles.marker} aria-hidden="true">
              {step.status === 'ok' ? '✓' : step.status === 'error' ? '!' : index + 1}
            </span>
            <div className={styles.stepBody}>
              <div className={styles.stepHead}>
                <strong>{stepLabel(step.name)}</strong>
                <span className={styles.badge} data-status={step.status}>
                  {STATUS_TEXT[step.status]}
                </span>
                <span className={styles.ms}>{step.ms} ms</span>
              </div>
              <p className={styles.summary}>{step.summary}</p>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
