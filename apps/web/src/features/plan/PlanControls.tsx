import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Segmented } from '@/components/ui/Segmented';
import {
  DAY_OPTIONS,
  MINUTES_OPTIONS,
  type DaysValue,
  type MinutesValue,
} from './usePlan';
import styles from './PlanControls.module.css';

export interface PlanControlsProps {
  days: DaysValue;
  minutes: MinutesValue;
  loading: boolean;
  canGenerate: boolean;
  onDays: (value: DaysValue) => void;
  onMinutes: (value: MinutesValue) => void;
  onGenerate: () => void;
  onOpenPreferences: () => void;
}

/** 计划参数卡：天数 / 单餐时长 / 我的偏好 / 生成按钮 */
export function PlanControls({
  days,
  minutes,
  loading,
  canGenerate,
  onDays,
  onMinutes,
  onGenerate,
  onOpenPreferences,
}: PlanControlsProps) {
  return (
    <Card
      title="生成饮食计划"
      subtitle="按天分配、按到期顺序消耗；过期食材绝不进计划"
      actions={
        <div className={styles.actions}>
          <Button variant="ghost" size="sm" onClick={onOpenPreferences}>
            我的偏好
          </Button>
          <Button onClick={onGenerate} loading={loading} disabled={!canGenerate}>
            生成计划
          </Button>
        </div>
      }
    >
      <div className={styles.controls}>
        <div className={styles.control}>
          <span className={styles.controlLabel}>计划天数</span>
          <Segmented
            ariaLabel="计划天数"
            options={DAY_OPTIONS}
            value={days}
            onChange={onDays}
            disabled={loading}
          />
        </div>
        <div className={styles.control}>
          <span className={styles.controlLabel}>单餐时长上限</span>
          <Segmented
            ariaLabel="单餐时长上限"
            options={MINUTES_OPTIONS}
            value={minutes}
            onChange={onMinutes}
            disabled={loading}
          />
        </div>
      </div>
      <p className={styles.note}>
        按 1 人份安排（2 人份当前同样按 1 人份配餐）；每餐都挂真实 recipe_id 与引用，方便核对。
      </p>
    </Card>
  );
}
