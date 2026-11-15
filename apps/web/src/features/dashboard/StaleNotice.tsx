import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import { Notice } from '@/components/ui/Notice';
import styles from './StaleNotice.module.css';

export interface StaleNoticeProps {
  /** stale_days > 3 的食材数量（0 时不渲染） */
  count: number;
}

/** §6.14 首页提示条：可关闭，点按直达对账页签 */
export function StaleNotice({ count }: StaleNoticeProps) {
  const [dismissed, setDismissed] = useState(false);
  const navigate = useNavigate();

  if (dismissed || count <= 0) return null;

  return (
    <Notice
      tone="warn"
      title={`有 ${count} 样食材超过 3 天未核验`}
      action={
        <div className={styles.actions}>
          <Button size="sm" onClick={() => navigate('/capture?tab=reconcile')}>
            去拍对账
          </Button>
          <Button variant="ghost" size="sm" onClick={() => setDismissed(true)}>
            知道了
          </Button>
        </div>
      }
    >
      库存可能和冰箱里的实际情况不一致，拍一张照片就能把差异同步回来。
    </Notice>
  );
}
