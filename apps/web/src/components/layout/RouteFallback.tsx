import { Skeleton } from '@/components/ui/Skeleton';
import styles from './RouteFallback.module.css';

/** 路由懒加载期间的骨架屏，保持布局高度不跳动 */
export function RouteFallback() {
  return (
    <div className={styles.wrap} role="status" aria-label="页面加载中">
      <div className={styles.block}>
        <Skeleton width="180px" height="28px" radius="var(--radius-md)" />
        <Skeleton lines={2} height="14px" />
      </div>
      <div className={styles.block}>
        <Skeleton width="120px" height="20px" radius="var(--radius-md)" />
        <Skeleton height="96px" radius="var(--radius-md)" />
      </div>
      <div className={styles.block}>
        <Skeleton width="140px" height="20px" radius="var(--radius-md)" />
        <Skeleton height="140px" radius="var(--radius-md)" />
      </div>
    </div>
  );
}
