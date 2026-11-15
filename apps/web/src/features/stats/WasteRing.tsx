import { formatPercent } from '@/lib/format';
import styles from './WasteRing.module.css';

export interface WasteRingProps {
  /** 0–1 */
  wasteRate: number;
  savedGrams: number;
  thrownGrams: number;
}

const SIZE = 168;
const STROKE = 16;
const RADIUS = (SIZE - STROKE) / 2;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

/** 手写 SVG 环图：绿色 = 吃掉的比例，红色 = 扔掉的比例 */
export function WasteRing({ wasteRate, savedGrams, thrownGrams }: WasteRingProps) {
  const safeRate = Math.min(1, Math.max(0, wasteRate));
  const savedArc = CIRCUMFERENCE * (1 - safeRate);
  const thrownArc = CIRCUMFERENCE * safeRate;
  const center = SIZE / 2;

  return (
    <div className={styles.wrap}>
      <svg
        className={styles.chart}
        viewBox={`0 0 ${SIZE} ${SIZE}`}
        role="img"
        aria-label={`浪费率 ${formatPercent(safeRate, 1)}，吃掉 ${Math.round(savedGrams)} 克，扔掉 ${Math.round(thrownGrams)} 克`}
      >
        <circle cx={center} cy={center} r={RADIUS} className={styles.track} strokeWidth={STROKE} />
        <circle
          cx={center}
          cy={center}
          r={RADIUS}
          className={styles.saved}
          strokeWidth={STROKE}
          strokeDasharray={`${savedArc} ${CIRCUMFERENCE}`}
          transform={`rotate(-90 ${center} ${center})`}
        />
        <circle
          cx={center}
          cy={center}
          r={RADIUS}
          className={styles.thrown}
          strokeWidth={STROKE}
          strokeDasharray={`${thrownArc} ${CIRCUMFERENCE}`}
          strokeDashoffset={-savedArc}
          transform={`rotate(-90 ${center} ${center})`}
        />
        <text x={center} y={center - 2} className={styles.value} textAnchor="middle">
          {formatPercent(safeRate, 1)}
        </text>
        <text x={center} y={center + 20} className={styles.caption} textAnchor="middle">
          浪费率
        </text>
      </svg>

      <ul className={styles.legend}>
        <li data-tone="good">
          <span className={styles.dot} aria-hidden="true" />
          吃掉 {Math.round(savedGrams)} g
        </li>
        <li data-tone="bad">
          <span className={styles.dot} aria-hidden="true" />
          扔掉 {Math.round(thrownGrams)} g
        </li>
      </ul>
    </div>
  );
}
