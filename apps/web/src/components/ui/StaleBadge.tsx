import styles from './StaleBadge.module.css';

export interface StaleBadgeProps {
  /** 距上次核验的天数（> 3 才展示） */
  days: number;
}

/** §6.14 新鲜度角标：提醒这份食材的库存数据可能过期 */
export function StaleBadge({ days }: StaleBadgeProps) {
  return (
    <span className={styles.badge} title={`距上次核验 ${days} 天，建议拍一张对账`}>
      {days} 天未核验
    </span>
  );
}
