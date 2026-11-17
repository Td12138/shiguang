import { useId } from 'react';
import type { StatsTrendPoint } from '@/lib/api';
import { shortDate } from '@/lib/format';
import styles from './TrendChart.module.css';

export interface TrendChartProps {
  points: StatsTrendPoint[];
}

const WIDTH = 680;
const HEIGHT = 220;
const PAD_X = 16;
const PAD_TOP = 12;
const PAD_BOTTOM = 30;
const INNER_W = WIDTH - PAD_X * 2;
const INNER_H = HEIGHT - PAD_TOP - PAD_BOTTOM;
const MAX_BAR_WIDTH = 18;
const LABEL_EVERY = 5;
const GRID_LINES = [0.25, 0.5, 0.75, 1];
const HATCH_SIZE = 6;

/** 手写 SVG 双色堆叠柱：绿色 = 吃掉，斜纹红 = 扔掉，单位克 */
export function TrendChart({ points }: TrendChartProps) {
  const hatchId = `thrown-hatch-${useId().replace(/:/g, '')}`;
  const totals = points.map((point) => point.saved + point.thrown);
  const max = Math.max(1, ...totals);
  const step = points.length > 0 ? INNER_W / points.length : INNER_W;
  const barWidth = Math.max(2, Math.min(MAX_BAR_WIDTH, step * 0.62));
  const savedTotal = points.reduce((sum, point) => sum + point.saved, 0);
  const thrownTotal = points.reduce((sum, point) => sum + point.thrown, 0);

  return (
    <figure className={styles.wrap}>
      <svg
        className={styles.chart}
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-label={`每日趋势：区间内吃掉 ${Math.round(savedTotal)} 克，扔掉 ${Math.round(thrownTotal)} 克`}
      >
        <defs>
          {/* 斜纹：灰度/色盲下「扔掉」也能和「吃掉」区分 */}
          <pattern
            id={hatchId}
            width={HATCH_SIZE}
            height={HATCH_SIZE}
            patternUnits="userSpaceOnUse"
            patternTransform="rotate(45)"
          >
            <rect width={HATCH_SIZE} height={HATCH_SIZE} className={styles.thrown} />
            <line x1="0" y1="0" x2="0" y2={HATCH_SIZE} className={styles.thrownStripe} strokeWidth="2" />
          </pattern>
        </defs>
        {GRID_LINES.map((ratio) => {
          const y = PAD_TOP + INNER_H * (1 - ratio);
          return (
            <line
              key={ratio}
              x1={PAD_X}
              y1={y}
              x2={WIDTH - PAD_X}
              y2={y}
              className={styles.gridLine}
            />
          );
        })}
        <line
          x1={PAD_X}
          y1={PAD_TOP + INNER_H}
          x2={WIDTH - PAD_X}
          y2={PAD_TOP + INNER_H}
          className={styles.axis}
        />
        {points.map((point, index) => {
          const savedHeight = (point.saved / max) * INNER_H;
          const thrownHeight = (point.thrown / max) * INNER_H;
          const x = PAD_X + step * index + (step - barWidth) / 2;
          const savedY = PAD_TOP + INNER_H - savedHeight;
          const thrownY = savedY - thrownHeight;
          const showLabel = index % LABEL_EVERY === 0 || index === points.length - 1;

          return (
            <g key={point.date}>
              {point.saved > 0 ? (
                <rect
                  x={x}
                  y={savedY}
                  width={barWidth}
                  height={Math.max(1, savedHeight)}
                  rx={4}
                  className={styles.saved}
                >
                  <title>{`${shortDate(point.date)} 吃掉 ${Math.round(point.saved)} g`}</title>
                </rect>
              ) : null}
              {point.thrown > 0 ? (
                <rect
                  x={x}
                  y={thrownY}
                  width={barWidth}
                  height={Math.max(1, thrownHeight)}
                  rx={4}
                  className={styles.thrown}
                  style={{ fill: `url(#${hatchId})` }}
                >
                  <title>{`${shortDate(point.date)} 扔掉 ${Math.round(point.thrown)} g`}</title>
                </rect>
              ) : null}
              {showLabel ? (
                <text
                  x={x + barWidth / 2}
                  y={HEIGHT - 8}
                  className={styles.label}
                  textAnchor="middle"
                >
                  {shortDate(point.date)}
                </text>
              ) : null}
            </g>
          );
        })}
      </svg>

      <figcaption className={styles.legend}>
        <span data-tone="good">
          <i aria-hidden="true" />
          吃掉
        </span>
        <span data-tone="bad">
          <i aria-hidden="true" />
          扔掉
        </span>
        <span className={styles.scale}>纵轴按当日总量缩放 · 单位克</span>
      </figcaption>
    </figure>
  );
}
