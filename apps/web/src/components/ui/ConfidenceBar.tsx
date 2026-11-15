import { formatScore } from '@/lib/format';
import styles from './ConfidenceBar.module.css';

/** 低于该阈值标黄（契约 §6.2：置信度 < 0.7 需提示） */
const LOW_CONFIDENCE = 0.7;

export interface ConfidenceBarProps {
  /** 0–1 */
  value: number;
  label?: string;
  /** 紧凑模式：不显示说明行 */
  compact?: boolean;
}

/** 置信度 / 匹配度可视化：条 + 百分比，低置信度自动变黄 */
export function ConfidenceBar({ value, label = '置信度', compact = false }: ConfidenceBarProps) {
  const clamped = Math.min(1, Math.max(0, value));
  const low = clamped < LOW_CONFIDENCE;

  return (
    <div className={styles.wrap} data-low={low || undefined}>
      <div className={styles.head}>
        <span className={styles.label}>{label}</span>
        <span className={styles.value}>{formatScore(clamped)}</span>
      </div>
      <div
        className={styles.track}
        role="meter"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(clamped * 100)}
        aria-label={`${label} ${formatScore(clamped)}`}
      >
        <span className={styles.fill} style={{ width: `${clamped * 100}%` }} />
      </div>
      {compact ? null : low ? (
        <p className={styles.hint}>置信度偏低，请人工确认</p>
      ) : null}
    </div>
  );
}
