import type { CSSProperties } from 'react';
import styles from './Skeleton.module.css';

export interface SkeletonProps {
  width?: string;
  height?: string;
  radius?: string;
  /** >1 时渲染多行文本占位，最后一行收窄 */
  lines?: number;
  className?: string;
}

/** 加载占位：纯 CSS 呼吸动画，无第三方依赖 */
export function Skeleton({
  width = '100%',
  height = '16px',
  radius = 'var(--radius-sm)',
  lines = 1,
  className,
}: SkeletonProps) {
  const count = Math.max(1, Math.round(lines));
  const classes = [styles.wrap, className].filter(Boolean).join(' ');

  return (
    <div className={classes} aria-hidden="true">
      {Array.from({ length: count }, (_, index) => {
        const isLast = index === count - 1;
        const style: CSSProperties = {
          width: isLast && count > 1 ? '62%' : width,
          height,
          borderRadius: radius,
        };
        return <span key={index} className={styles.bar} style={style} />;
      })}
    </div>
  );
}
