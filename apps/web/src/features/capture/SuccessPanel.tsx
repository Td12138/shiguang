import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Notice } from '@/components/ui/Notice';
import styles from './SuccessPanel.module.css';

export interface SuccessPanelProps {
  /** 入库条数（演示模式下为「按演示继续」的条数） */
  added: number;
  /** true = 后端未连，没有真正写入数据库 */
  demoSubmit: boolean;
  onReset: () => void;
  onPlan: () => void;
}

/** 入库完成：就地给出结果 + 下一步（生成饮食计划） */
export function SuccessPanel({ added, demoSubmit, onReset, onPlan }: SuccessPanelProps) {
  return (
    <Card tone="accent">
      <div className={styles.wrap}>
        <span className={styles.badge} aria-hidden="true">
          ✓
        </span>
        <h2 className={styles.title}>{demoSubmit ? `演示：${added} 条未写入` : `已入库 ${added} 条`}</h2>
        <p className={styles.desc}>
          {demoSubmit
            ? '后端未连接，这次只走通流程，没有写进数据库。接上后端再确认一次即可真正入库。'
            : '库存已更新，首页的临期倒计时会立刻反映出来。'}
        </p>

        {demoSubmit ? (
          <Notice tone="warn" title="演示模式">
            数据未落库；「生成 3 天饮食计划」同样会使用内置样例。
          </Notice>
        ) : null}

        <div className={styles.actions}>
          <Button onClick={onPlan}>生成 3 天饮食计划</Button>
          <Button variant="secondary" onClick={onReset}>
            再拍一张
          </Button>
        </div>
      </div>
    </Card>
  );
}
