import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { deletePreference, describeApiError } from '@/lib/api';
import type { LearnedPreference } from '@/lib/api';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { DemoBanner } from '@/components/ui/DemoBanner';
import { EmptyState } from '@/components/ui/EmptyState';
import { Modal } from '@/components/ui/Modal';
import { Notice } from '@/components/ui/Notice';
import { Skeleton } from '@/components/ui/Skeleton';
import { useToast } from '@/components/ui/Toast';
import { PlanBody } from './PlanBody';
import { PlanControls } from './PlanControls';
import { PlanDiff } from './PlanDiff';
import { PreferencesPanel } from './PreferencesPanel';
import { ReviseComposer } from './ReviseComposer';
import { usePlan } from './usePlan';
import { staleByName } from '@/lib/freshness';
import styles from './PlanPage.module.css';

export default function PlanPage() {
  const plan = usePlan();
  const { toast } = useToast();
  const navigate = useNavigate();
  const [prefsOpen, setPrefsOpen] = useState(false);
  const staleDays = useMemo(() => staleByName(plan.inventory), [plan.inventory]);

  const hasPlan = plan.plan !== null && plan.plan.days.length > 0;
  const emptyPlan = plan.plan !== null && plan.plan.days.length === 0;

  const revoke = async (preference: LearnedPreference): Promise<void> => {
    try {
      await deletePreference(preference.id);
      toast(`已撤销：${preference.text}`, 'info');
    } catch (err) {
      toast(describeApiError(err), 'error');
    }
  };

  const handleRevise = async (instruction: string): Promise<void> => {
    const outcome = await plan.revise(instruction);
    if (!outcome.ok) {
      toast(outcome.message ?? '调整失败', 'error');
      return;
    }
    if (outcome.changed.length === 0) {
      toast('这次没能改，原因见下方', 'info');
    } else {
      toast(`已调整 ${outcome.changed.length} 处`, 'success');
    }
    outcome.learned.forEach((preference) => {
      toast(`已记住：${preference.text}`, 'success', {
        action: { label: '撤销', onAction: () => void revoke(preference) },
      });
    });
  };

  return (
    <div className={`page-stack ${hasPlan ? styles.withComposer : ''}`}>
      {plan.demo ? (
        <DemoBanner
          message="计划接口没有响应，下面这份是内置样例；改计划与偏好的写入都需要真实后端。"
          onRetry={() => void plan.generate()}
        />
      ) : null}

      <PlanControls
        days={plan.days}
        minutes={plan.minutes}
        loading={plan.loading}
        canGenerate={plan.inventory.length > 0}
        onDays={plan.setDays}
        onMinutes={plan.setMinutes}
        onGenerate={() => void plan.generate()}
        onOpenPreferences={() => setPrefsOpen(true)}
      />

      {plan.reviseError ? (
        <Notice tone="error" title="调整失败，计划未改动">
          {plan.reviseError}
        </Notice>
      ) : null}

      <PlanDiff diff={plan.diff} onDismiss={plan.dismissDiff} />

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
      ) : emptyPlan ? (
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
      ) : plan.plan ? (
        <PlanBody plan={plan.plan} inventoryTotal={plan.inventory.length} staleDays={staleDays} />
      ) : null}

      {hasPlan ? <ReviseComposer revising={plan.revising} onSubmit={(text) => void handleRevise(text)} /> : null}

      <Modal open={prefsOpen} title="我的偏好" onClose={() => setPrefsOpen(false)}>
        <PreferencesPanel demo={plan.demo} />
      </Modal>
    </div>
  );
}
