import styles from './StatTile.module.css';

export interface StatTileProps {
  label: string;
  value: string;
  unit?: string;
  hint?: string;
  tone?: 'default' | 'good' | 'bad';
}

/** 统计数字卡：一个大数字 + 一行口径说明 */
export function StatTile({ label, value, unit, hint, tone = 'default' }: StatTileProps) {
  return (
    <div className={styles.tile} data-tone={tone}>
      <span className={styles.label}>{label}</span>
      <p className={styles.value}>
        {value}
        {unit ? <span className={styles.unit}>{unit}</span> : null}
      </p>
      {hint ? <span className={styles.hint}>{hint}</span> : null}
    </div>
  );
}
