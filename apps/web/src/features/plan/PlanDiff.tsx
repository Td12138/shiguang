import type { PlanChange } from '@/lib/api';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Notice } from '@/components/ui/Notice';
import { dayLabel } from '@/lib/format';
import styles from './PlanDiff.module.css';

export interface PlanDiffState {
  changed: PlanChange[];
  warnings: string[];
}

export interface PlanDiffProps {
  diff: PlanDiffState | null;
  onDismiss: () => void;
}

/** 本次调整的 diff：改成功了逐条列出，没改成功就显示后端给的原因 */
export function PlanDiff({ diff, onDismiss }: PlanDiffProps) {
  if (!diff) return null;

  const reason = diff.warnings[0] ?? '后端没有说明原因';
  const extraWarnings = diff.changed.length > 0 ? diff.warnings : [];

  return (
    <Card
      title={diff.changed.length > 0 ? `本次调整（${diff.changed.length} 处）` : '本次调整'}
      subtitle={diff.changed.length > 0 ? '未涉及的餐次保持不变' : '没有产生改动'}
      actions={
        <Button variant="ghost" size="sm" onClick={onDismiss}>
          关闭
        </Button>
      }
    >
      {diff.changed.length === 0 ? (
        <Notice tone="warn" title="这次没能改">
          {reason}
        </Notice>
      ) : (
        <ul className={styles.list}>
          {diff.changed.map((change) => (
            <li key={`${change.date}-${change.slot}`} className={styles.item}>
              <span className={styles.when}>
                {dayLabel(change.date)} · {change.slot}
              </span>
              <span className={styles.from}>{change.from}</span>
              <span className={styles.arrow} aria-hidden="true">
                →
              </span>
              <span className={styles.to}>{change.to}</span>
              <span className={styles.reason}>{change.reason}</span>
            </li>
          ))}
        </ul>
      )}

      {extraWarnings.length > 0 ? (
        <Notice tone="warn" title="调整提示">
          <ul className={styles.warnings}>
            {extraWarnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </Notice>
      ) : null}
    </Card>
  );
}
