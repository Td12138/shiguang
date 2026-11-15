import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { DemoBanner } from '@/components/ui/DemoBanner';
import { EmptyState } from '@/components/ui/EmptyState';
import { Notice } from '@/components/ui/Notice';
import { Segmented } from '@/components/ui/Segmented';
import { Skeleton } from '@/components/ui/Skeleton';
import { CoverageBar } from './CoverageBar';
import { PlanDayColumn } from './PlanDayColumn';
import { ShoppingList } from './ShoppingList';
import { DAY_OPTIONS, MINUTES_OPTIONS, usePlan } from './usePlan';
import styles from './PlanPage.module.css';

export default function PlanPage() {
  const plan = usePlan();
  const navigate = useNavigate();
  const empty = plan.plan !== null && plan.plan.days.length === 0;

  return (
    <div className="page-stack">
      {plan.demo ? (
        <DemoBanner
          message="计划接口没有响应（后端 /api/plan/meals 可能还没上线），下面这份是内置样例，不是按你的库存算出来的。"
          onRetry={() => void plan.generate()}
        />
      ) : null}

      <Card
        title="生成饮食计划"
        subtitle="按天分配、按到期顺序消耗；过期食材绝不进计划"
        actions={
          <Button
            onClick={() => void plan.generate()}
            loading={plan.loading}
            disabled={plan.inventory.length === 0}
          >
            生成计划
          </Button>
        }
      >
        <div className={styles.controls}>
          <div className={styles.control}>
            <span className={styles.controlLabel}>计划天数</span>
            <Segmented
              ariaLabel="计划天数"
              options={DAY_OPTIONS}
              value={plan.days}
              onChange={plan.setDays}
              disabled={plan.loading}
            />
          </div>
          <div className={styles.control}>
            <span className={styles.controlLabel}>单餐时长上限</span>
            <Segmented
              ariaLabel="单餐时长上限"
              options={MINUTES_OPTIONS}
              value={plan.minutes}
              onChange={plan.setMinutes}
              disabled={plan.loading}
            />
          </div>
        </div>
        <p className={styles.note}>
          按 1 人份安排（2 人份当前同样按 1 人份配餐）；每餐都挂真实 recipe_id 与引用，方便核对。
        </p>
      </Card>

      {plan.error ? (
        <Notice
          tone="error"
          title="生成失败"
          action={
            <Button variant="secondary" size="sm" onClick={() => void plan.generate()}>
              重试
            </Button>
          }
        >
          {plan.error}
        </Notice>
      ) : null}

      {plan.loading ? (
        <div className={styles.skeletonGrid}>
          <Skeleton height="180px" radius="var(--radius-lg)" />
          <Skeleton height="180px" radius="var(--radius-lg)" />
          <Skeleton height="180px" radius="var(--radius-lg)" />
        </div>
      ) : plan.inventory.length === 0 && plan.plan === null ? (
        <Card>
          <EmptyState
            title="冰箱里还没有食材"
            description="计划需要真实库存才能按到期顺序分配；先拍一张冰箱照片入库，再回来生成。"
            action={<Button onClick={() => navigate('/capture')}>去拍照入库</Button>}
          />
        </Card>
      ) : plan.plan === null ? (
        <Card>
          <EmptyState
            title="还没有生成计划"
            description="选好天数与单餐时长，点右上角「生成计划」；有库存才能排出真实的用量分配。"
            action={<Button onClick={() => void plan.generate()}>现在生成</Button>}
          />
        </Card>
      ) : empty ? (
        <Card>
          <EmptyState
            title="这段时间排不出可用计划"
            description="可能库存太少，或时间上限太紧。放宽时长、补几样食材再试。"
            action={
              <Button variant="secondary" onClick={() => void plan.generate()}>
                换个条件再试
              </Button>
            }
          />
        </Card>
      ) : (
        <>
          <CoverageBar coverage={plan.plan.coverage} inventoryTotal={plan.inventory.length} />

          {plan.plan.warnings.length > 0 ? (
            <Notice tone="warn" title="计划提示">
              <ul className={styles.warnings}>
                {plan.plan.warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            </Notice>
          ) : null}

          <div className={styles.layout}>
            <div className={styles.days}>
              {plan.plan.days.map((day, index) => (
                <PlanDayColumn key={day.date} day={day} index={index} />
              ))}
            </div>
            <ShoppingList items={plan.plan.shopping} />
          </div>
        </>
      )}
    </div>
  );
}
