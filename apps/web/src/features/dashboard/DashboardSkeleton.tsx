import { Skeleton } from '@/components/ui/Skeleton';
import styles from './DashboardSkeleton.module.css';

/** 首页骨架：区块高度与真实内容接近，避免加载完成时跳动 */
export function DashboardSkeleton() {
  return (
    <div className={styles.wrap} role="status" aria-label="正在读取冰箱数据">
      <div className={styles.urgent}>
        <Skeleton width="200px" height="26px" />
        <Skeleton width="320px" height="14px" />
        <div className={styles.cards}>
          <Skeleton height="132px" radius="var(--radius-md)" />
          <Skeleton height="132px" radius="var(--radius-md)" />
          <Skeleton height="132px" radius="var(--radius-md)" />
        </div>
      </div>
      <div className={styles.block}>
        <Skeleton width="140px" height="22px" />
        <Skeleton lines={3} height="14px" />
      </div>
      <div className={styles.block}>
        <Skeleton width="120px" height="22px" />
        <Skeleton height="160px" radius="var(--radius-md)" />
      </div>
    </div>
  );
}
