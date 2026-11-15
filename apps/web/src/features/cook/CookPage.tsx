import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import type { RecipeRecommendation } from '@/lib/api';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { DemoBanner } from '@/components/ui/DemoBanner';
import { EmptyState } from '@/components/ui/EmptyState';
import { Notice } from '@/components/ui/Notice';
import { Skeleton } from '@/components/ui/Skeleton';
import { useToast } from '@/components/ui/Toast';
import { ConsumeModal } from './ConsumeModal';
import type { ConsumeLine } from './consume';
import { CookTimeline } from './CookTimeline';
import { IngredientPicker } from './IngredientPicker';
import { SuggestionSection } from './SuggestionSection';
import { useCook } from './useCook';
import { MAX_SEQUENCE_RECIPES, useCookSequence } from './useCookSequence';
import styles from './CookPage.module.css';

/** 「临期」口径与 useCook 一致：3 天内到期 */
const URGENT_DAYS = 3;

export default function CookPage() {
  const cook = useCook();
  const sequence = useCookSequence();
  const { toast } = useToast();
  const navigate = useNavigate();
  const [pending, setPending] = useState<RecipeRecommendation | null>(null);

  const namesOf = (ids: string[]): string =>
    ids.map((id) => cook.inventory.find((item) => item.id === id)?.name ?? '库存条目').join('、');

  const handleSuggest = async (): Promise<void> => {
    sequence.reset();
    await cook.suggest();
  };

  const handleSequence = async (): Promise<void> => {
    const ok = await sequence.run();
    toast(ok ? '已生成备菜时间轴' : '没能生成时间轴，看看提示', ok ? 'success' : 'error');
  };

  const handlePick = (recipeId: string): void => {
    const result = sequence.togglePick(recipeId);
    if (result === 'limit') toast(`一次最多 ${MAX_SEQUENCE_RECIPES} 道，先移出一道`, 'info');
  };

  const finish = async (recipe: RecipeRecommendation, lines: ConsumeLine[]): Promise<void> => {
    const outcome = await cook.consume(recipe, lines);
    if (outcome.ok) toast(`已扣减：${namesOf(outcome.consumed)}`, 'success');
    else toast(outcome.message ?? '扣减失败', 'error');
  };

  const handleCooked = async (recipe: RecipeRecommendation): Promise<void> => {
    // 优先用 uses[].inventory_id 直接扣减；没有 id 时按食材名对上库存；都对不上才弹确认
    const ids = (recipe.uses ?? []).flatMap((use) => {
      if (use.inventory_id && cook.inventory.some((item) => item.id === use.inventory_id)) {
        return [use.inventory_id];
      }
      const byName = cook.inventory.find((item) => item.name === use.name);
      return byName ? [byName.id] : [];
    });
    const complete = (recipe.uses ?? []).length > 0 && ids.length === (recipe.uses ?? []).length;
    if (complete) await finish(recipe, ids.map((id) => ({ id })));
    else setPending(recipe);
  };

  return (
    <div className="page-stack">
      {cook.demo ? (
        <DemoBanner
          message="库存或建议接口没有响应，页面上的食材与菜谱来自内置样例；扣减只在真实后端上生效。"
          onRetry={cook.reset}
        />
      ) : null}

      {cook.error ? (
        <Notice
          tone="error"
          title="请求没有成功"
          action={
            <Button variant="secondary" size="sm" onClick={() => void handleSuggest()}>
              重试
            </Button>
          }
        >
          {cook.error}
        </Notice>
      ) : null}

      {cook.loading ? (
        <Card title="① 选食材" subtitle="正在读取冰箱库存">
          <Skeleton lines={2} height="14px" />
          <div className={styles.chipSkeleton}>
            <Skeleton width="96px" height="34px" radius="var(--radius-pill)" />
            <Skeleton width="120px" height="34px" radius="var(--radius-pill)" />
            <Skeleton width="88px" height="34px" radius="var(--radius-pill)" />
          </div>
        </Card>
      ) : cook.inventory.length === 0 ? (
        <Card>
          <EmptyState
            title="冰箱里还没有食材"
            description="先拍一张冰箱照片入库，再让 AI 按临期顺序安排今天吃什么。"
            action={<Button onClick={() => navigate('/capture')}>去拍照入库</Button>}
          />
        </Card>
      ) : (
        <Card
          title="① 选食材"
          subtitle={`默认选中 ${cook.inventory.filter((item) => item.days_left <= URGENT_DAYS).length} 样 3 天内到期的食材；也可以自己挑`}
          actions={
            <div className={styles.pickerActions}>
              <Button variant="ghost" size="sm" onClick={cook.selectExpiring}>
                选临期
              </Button>
              <Button variant="ghost" size="sm" onClick={cook.clearSelection}>
                清空
              </Button>
            </div>
          }
        >
          <IngredientPicker
            inventory={cook.inventory}
            selected={cook.selected}
            onToggle={cook.toggle}
            disabled={cook.suggesting}
          />
          <div className={styles.footer}>
            <p className={styles.hint}>
              已选 {cook.selected.length} 样；建议在 30 分钟内能做完，理由与引用都可核对。
            </p>
            <Button
              onClick={() => void handleSuggest()}
              loading={cook.suggesting}
              disabled={cook.selected.length === 0}
            >
              给我方案
            </Button>
          </div>
        </Card>
      )}

      <SuggestionSection
        suggestion={cook.suggestion}
        suggesting={cook.suggesting}
        consuming={cook.consuming}
        doneIds={cook.doneIds}
        onSuggest={() => void handleSuggest()}
        onCooked={(recipe) => void handleCooked(recipe)}
        picked={sequence.picked}
        canPickMore={sequence.canPickMore}
        onTogglePick={handlePick}
        onSequence={() => void handleSequence()}
        sequencing={sequence.loading}
      />

      {sequence.sequence || sequence.loading || sequence.error ? (
        <CookTimeline
          sequence={sequence.sequence}
          loading={sequence.loading}
          error={sequence.error}
          onRetry={() => void handleSequence()}
          onClose={sequence.reset}
        />
      ) : null}

      <ConsumeModal
        recipe={pending}
        inventory={cook.inventory}
        onClose={() => setPending(null)}
        onConfirm={(lines) => {
          const recipe = pending;
          setPending(null);
          if (recipe) void finish(recipe, lines);
        }}
        submitting={cook.consuming}
      />
    </div>
  );
}
