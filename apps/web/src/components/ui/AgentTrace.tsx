import type { AgentRun, AgentStep } from '@/lib/api';
import { Skeleton } from './Skeleton';
import styles from './AgentTrace.module.css';

/** 契约 §9 的步骤名 → 中文标签（plan/meals 的 allocate 也在此列出） */
const STEP_LABELS: Record<string, string> = {
  understand: '理解需求',
  plan: '读取库存并排序',
  allocate: '按天分配用量',
  retrieve: '检索菜谱',
  compose: '组织建议',
  verify: '规则校验',
};

const STATUS_TEXT: Record<string, string> = {
  ok: '完成',
  degraded: '降级',
  error: '失败',
  empty: '无结果',
  skipped: '跳过',
  running: '进行中',
  pending: '等待',
};

const RUN_STATE_TEXT: Record<string, string> = {
  ok: '全部通过',
  degraded: '已降级',
  failed: '执行失败',
  running: '进行中',
};

const OK_MARK = 'ok';
const ERROR_MARK = 'error';

function stepLabel(name: string): string {
  return STEP_LABELS[name] ?? name;
}

function statusText(status: string): string {
  return STATUS_TEXT[status] ?? status;
}

function markerOf(status: string, index: number): string {
  if (status === OK_MARK) return '✓';
  if (status === ERROR_MARK) return '!';
  if (status === 'degraded') return '~';
  if (status === 'empty' || status === 'skipped') return '–';
  return `${index + 1}`;
}

export interface AgentTraceProps {
  run: AgentRun | null;
  loading?: boolean;
  error?: string | null;
  /** 流式进度里不需要展示 run id */
  showRunId?: boolean;
}

/** Agent 步骤时间线：让「规划 → 调工具 → 自检」的过程可回放（契约 §9） */
export function AgentTrace({
  run,
  loading = false,
  error = null,
  showRunId = true,
}: AgentTraceProps) {
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
        {showRunId ? <span className={styles.runId}>run · {run.id}</span> : <span />}
        <span className={styles.state} data-state={run.state}>
          {RUN_STATE_TEXT[run.state] ?? run.state}
        </span>
      </div>
      <ol className={styles.timeline}>
        {run.steps.map((step: AgentStep, index) => (
          <li key={`${step.name}-${index}`} className={styles.step} data-status={step.status}>
            <span className={styles.marker} aria-hidden="true">
              {markerOf(step.status, index)}
            </span>
            <div className={styles.stepBody}>
              <div className={styles.stepHead}>
                <strong>{stepLabel(step.name)}</strong>
                <span className={styles.badge} data-status={step.status}>
                  {statusText(step.status)}
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

