import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import { DemoBanner } from '@/components/ui/DemoBanner';
import { EmptyState } from '@/components/ui/EmptyState';
import { Notice } from '@/components/ui/Notice';
import { countStale } from '@/lib/freshness';
import { DashboardSkeleton } from './DashboardSkeleton';
import { FridgeOverview } from './FridgeOverview';
import { SuggestionPanel } from './SuggestionPanel';
import { UrgentStrip } from './UrgentStrip';
import { StaleNotice } from './StaleNotice';
import { groupByCategory, pickExpiring } from './selectors';
import { useDashboard } from './useDashboard';
import styles from './DashboardPage.module.css';

export default function DashboardPage() {
  const { inventory, suggestion, loading, demo, error, reload } = useDashboard();
  const navigate = useNavigate();

  const expiring = useMemo(() => pickExpiring(inventory), [inventory]);
  const groups = useMemo(() => groupByCategory(inventory), [inventory]);
  const staleCount = useMemo(() => countStale(inventory), [inventory]);

  if (loading) {
    return (
      <div className="page-stack">
        <DashboardSkeleton />
      </div>
    );
  }

  if (error) {
    return (
      <div className="page-stack">
        <Notice
          tone="error"
          title="库存读取失败"
          action={
            <Button variant="secondary" size="sm" onClick={() => void reload()}>
              重试
            </Button>
          }
        >
          {error}
        </Notice>
      </div>
    );
  }

  if (inventory.length === 0) {
    return (
      <div className="page-stack">
        {demo ? <DemoBanner onRetry={reload} /> : null}
        <section className={styles.emptyCard}>
          <EmptyState
            title="冰箱还是空的"
            description="拍一张冰箱照片，识别出的食材会先进入校对清单，确认后才写进库存。或者先看看冰箱里到底剩了点什么。"
            action={
              <div className={styles.actions}>
                <Button onClick={() => navigate('/capture')}>去拍照入库</Button>
                <Button variant="secondary" onClick={() => void reload()}>
                  重新读取
                </Button>
              </div>
            }
          />
          <p className={styles.emptyNote}>
            没有照片也没关系：手工补一条库存同样可以开始记时效。
          </p>
        </section>
      </div>
    );
  }

  return (
    <div className="page-stack">
      {demo ? <DemoBanner onRetry={reload} /> : null}
      <StaleNotice count={staleCount} />
      <UrgentStrip items={expiring} />
      <SuggestionPanel suggestion={suggestion} loading={loading} onRefresh={reload} />
      <FridgeOverview groups={groups} total={inventory.length} />
    </div>
  );
}
