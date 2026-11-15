import type { CookSequence } from '@/lib/api';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Notice } from '@/components/ui/Notice';
import { Skeleton } from '@/components/ui/Skeleton';
import { useToast } from '@/components/ui/Toast';
import styles from './CookTimeline.module.css';

export interface CookTimelineProps {
  sequence: CookSequence | null;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
  onClose: () => void;
}

const DEGRADE_PREFIX = '已降级';

function buildText(sequence: CookSequence): string {
  const lines = [`备菜时间轴（共 ${sequence.total_minutes} 分钟）`];
  for (const step of sequence.steps) {
    const parallel =
      step.parallel_with.length > 0 ? `，与第 ${step.parallel_with.join('、')} 步同时` : '';
    lines.push(`${step.order}. ${step.at} ${step.action}（${step.minutes} 分钟${parallel}）`);
  }
  if (sequence.tips.length > 0) {
    lines.push('', '小提示：');
    sequence.tips.forEach((tip) => lines.push(`- ${tip}`));
  }
  return lines.join('\n');
}

/** 备菜流水线：总时长 + 步骤时间轴 + 并行标记 + 提示 + 复制清单 */
export function CookTimeline({ sequence, loading, error, onRetry, onClose }: CookTimelineProps) {
  const { toast } = useToast();

  const copy = async (): Promise<void> => {
    if (!sequence) return;
    try {
      await navigator.clipboard.writeText(buildText(sequence));
      toast('已复制清单，边做边看', 'success');
    } catch {
      toast('复制失败，请手动选择文本', 'error');
    }
  };

  const degraded = (sequence?.warnings ?? []).filter((warning) => warning.startsWith(DEGRADE_PREFIX));
  const others = (sequence?.warnings ?? []).filter((warning) => !warning.startsWith(DEGRADE_PREFIX));

  return (
    <Card
      title="备菜时间轴"
      subtitle={
        sequence
          ? `从 ${sequence.steps[0]?.at ?? '现在'} 开始 · 共 ${sequence.total_minutes} 分钟`
          : '把多道菜的步骤排成一条并行时间线'
      }
      actions={
        <div className={styles.actions}>
          {sequence ? (
            <Button variant="secondary" size="sm" onClick={() => void copy()}>
              复制清单
            </Button>
          ) : null}
          <Button variant="ghost" size="sm" onClick={onClose}>
            收起
          </Button>
        </div>
      }
    >
      {loading ? (
        <div className={styles.loading}>
          <Skeleton width="40%" height="20px" />
          <Skeleton lines={4} height="14px" />
        </div>
      ) : error ? (
        <Notice
          tone="error"
          title="没能排出时间轴"
          action={
            <Button variant="secondary" size="sm" onClick={onRetry}>
              重试
            </Button>
          }
        >
          {error}
        </Notice>
      ) : sequence ? (
        <>
          <div className={styles.summary}>
            <span className={styles.total}>
              {sequence.total_minutes}
              <em>分钟</em>
            </span>
            <span className={styles.count}>{sequence.steps.length} 步</span>
          </div>

          {sequence.tips.length > 0 ? (
            <div className={styles.tips}>
              <h3 className={styles.tipsTitle}>小提示</h3>
              <ul>
                {sequence.tips.map((tip) => (
                  <li key={tip}>{tip}</li>
                ))}
              </ul>
            </div>
          ) : null}

          <ol className={styles.steps}>
            {sequence.steps.map((step) => (
              <li key={step.order} className={styles.step}>
                <span className={styles.marker} aria-hidden="true">
                  {step.order}
                </span>
                <div className={styles.body}>
                  <div className={styles.line}>
                    <time className={styles.time}>{step.at}</time>
                    <strong className={styles.action}>{step.action}</strong>
                    <span className={styles.minutes}>{step.minutes} 分钟</span>
                  </div>
                  {step.parallel_with.length > 0 ? (
                    <span className={styles.parallel}>
                      与第 {step.parallel_with.join('、')} 步同时
                    </span>
                  ) : null}
                </div>
              </li>
            ))}
          </ol>

          {degraded.length > 0 ? (
            <Notice tone="warn" title="本次按规则版排序">
              <ul className={styles.warnings}>
                {degraded.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            </Notice>
          ) : null}

          {others.length > 0 ? (
            <Notice tone="info" title="排序提示">
              <ul className={styles.warnings}>
                {others.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            </Notice>
          ) : null}
        </>
      ) : (
        <p className={styles.empty}>
          还没生成时间轴。先在推荐卡上点「加入备菜」选 1–6 道，再点「开始做这几道」。
        </p>
      )}
    </Card>
  );
}
