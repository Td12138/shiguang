import type { ReconcileApplied } from '@/lib/api';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import styles from './ReconcileCapture.module.css';

export interface ReconcileResultPanelProps {
  applied: ReconcileApplied;
  onReset: () => void;
  onHome: () => void;
}

/** 应用成功后的结果卡：四类计数 + 下一步；下一轮从「全部保留」重新开始 */
export function ReconcileResultPanel({ applied, onReset, onHome }: ReconcileResultPanelProps) {
  return (
    <Card title="对账已应用" subtitle="动作已写入 events(kind=reconcile)，可回溯这次核验改了什么">
      <dl className={styles.applied}>
        <div>
          <dt>丢弃</dt>
          <dd>{applied.discarded}</dd>
        </div>
        <div>
          <dt>吃掉</dt>
          <dd>{applied.consumed}</dd>
        </div>
        <div>
          <dt>更新数量</dt>
          <dd>{applied.updated}</dd>
        </div>
        <div>
          <dt>新增</dt>
          <dd>{applied.added}</dd>
        </div>
      </dl>
      <p className={styles.appliedNote}>下一轮核对会从「全部保留」的默认动作重新开始。</p>
      <div className={styles.footer}>
        <Button variant="secondary" onClick={onReset}>
          再对一次
        </Button>
        <Button onClick={onHome}>回首页看库存</Button>
      </div>
    </Card>
  );
}
