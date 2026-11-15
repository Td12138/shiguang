import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Notice } from '@/components/ui/Notice';
import { ManualRowsEditor } from './ManualRowsEditor';
import type { ManualRowsState } from './useManualRows';
import styles from './ManualOnlyCard.module.css';

export interface ManualOnlyCardProps {
  manual: ManualRowsState;
  submitError: string | null;
  submitting: boolean;
  onSubmit: () => void;
  title?: string;
  subtitle?: string;
}

/** 识别不可用时的兜底：纯手动录入后直接入库 */
export function ManualOnlyCard({
  manual,
  submitError,
  submitting,
  onSubmit,
  title = '手动录入',
  subtitle = '识别不可用时也能先把食材记下来；名称可自动补全',
}: ManualOnlyCardProps) {
  return (
    <Card title={title} subtitle={subtitle}>
      <ManualRowsEditor manual={manual} addLabel="再加一样" disabled={submitting} />
      {submitError ? (
        <Notice tone="error" title="入库失败">
          {submitError}
        </Notice>
      ) : null}
      <div className={styles.footer}>
        <p className={styles.hint}>数量支持 0.5 这种小数；库外食材不计入碳账。</p>
        <Button
          onClick={onSubmit}
          loading={submitting}
          disabled={manual.items.length === 0 || manual.invalid}
        >
          确认入库 {manual.items.length} 条
        </Button>
      </div>
    </Card>
  );
}
