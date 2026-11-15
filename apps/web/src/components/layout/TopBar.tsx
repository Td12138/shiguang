import { todayLabel } from '@/lib/format';
import styles from './TopBar.module.css';

export interface TopBarProps {
  title: string;
  subtitle: string;
}

/** 顶部标题栏：左标题 + 右日期；移动端下移为两行 */
export function TopBar({ title, subtitle }: TopBarProps) {
  return (
    <header className={styles.bar}>
      <div className={styles.heading}>
        <p className={styles.subtitle}>{subtitle}</p>
        <h1 className={styles.title}>{title}</h1>
      </div>
      <p className={styles.date}>
        <time dateTime={new Date().toISOString().slice(0, 10)}>{todayLabel()}</time>
      </p>
    </header>
  );
}
