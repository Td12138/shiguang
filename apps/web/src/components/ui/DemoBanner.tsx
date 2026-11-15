import { Button } from './Button';
import styles from './DemoBanner.module.css';

export interface DemoBannerProps {
  /** 补充说明：哪部分数据是样例 */
  message?: string;
  onRetry?: () => void;
}

/**
 * 演示数据提示条（契约 §10.5：失败要可见，不静默假装成功）。
 * 只要任一接口回落 mock，页面顶部必须出现这一条。
 */
export function DemoBanner({ message, onRetry }: DemoBannerProps) {
  return (
    <div className={styles.wrap} role="status">
      <span className={styles.tag}>演示数据</span>
      <p className={styles.text}>
        {message ??
          '后端未连接（127.0.0.1:8720），当前展示内置样例，不是你的真实库存与真实检索结果。'}
      </p>
      {onRetry ? (
        <Button variant="secondary" size="sm" onClick={onRetry}>
          重试连接
        </Button>
      ) : null}
    </div>
  );
}
