import { Button } from '@/components/ui/Button';
import { useTour } from '@/components/tour/TourProvider';
import { todayLabel } from '@/lib/format';
import styles from './TopBar.module.css';

export interface TopBarProps {
  title: string;
  subtitle: string;
}

/** 顶部标题栏：左标题 + 右日期与「新手引导」入口；移动端下移为两行 */
export function TopBar({ title, subtitle }: TopBarProps) {
  const { start } = useTour();

  return (
    <header className={styles.bar}>
      <div className={styles.heading}>
        <p className={styles.subtitle}>{subtitle}</p>
        <h1 className={styles.title}>{title}</h1>
      </div>
      <div className={styles.meta}>
        <p className={styles.date}>
          <time dateTime={new Date().toISOString().slice(0, 10)}>{todayLabel()}</time>
        </p>
        <Button variant="ghost" size="sm" onClick={start} aria-label="重新观看新手引导">
          新手引导
        </Button>
      </div>
    </header>
  );
}
