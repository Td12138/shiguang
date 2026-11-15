import { useCallback, useEffect, useState } from 'react';
import { ApiError, loadInventory as fetchInventory, loadPlan, reviseMealPlan } from '@/lib/api';
import type { InventoryItem, LearnedPreference, MealPlan, PlanChange } from '@/lib/api';
import type { PlanDiffState } from './PlanDiff';

/** 契约 §6.8 默认 3 天；2/3/5 覆盖「今晚」「这一周」两类场景 */
export const DAY_OPTIONS = [
  { value: '2', label: '2 天' },
  { value: '3', label: '3 天' },
  { value: '5', label: '5 天' },
] as const;

export const MINUTES_OPTIONS = [
  { value: '20', label: '20 分钟' },
  { value: '30', label: '30 分钟' },
  { value: '45', label: '45 分钟' },
] as const;

export type DaysValue = (typeof DAY_OPTIONS)[number]['value'];
export type MinutesValue = (typeof MINUTES_OPTIONS)[number]['value'];

const DEFAULT_DAYS: DaysValue = '3';
const DEFAULT_MINUTES: MinutesValue = '30';
/** 暂不支持多人：单人或两人份都按 1 人份配餐，页面上写明 */
const SERVINGS = 1;

export interface ReviseOutcome {
  ok: boolean;
  changed: PlanChange[];
  learned: LearnedPreference[];
  message?: string;
}

export interface PlanState {
  days: DaysValue;
  minutes: MinutesValue;
  plan: MealPlan | null;
  inventory: InventoryItem[];
  loading: boolean;
  demo: boolean;
  error: string | null;
  revising: boolean;
  reviseError: string | null;
  diff: PlanDiffState | null;
  setDays: (value: DaysValue) => void;
  setMinutes: (value: MinutesValue) => void;
  generate: () => Promise<void>;
  revise: (instruction: string) => Promise<ReviseOutcome>;
  dismissDiff: () => void;
}

function messageOf(err: unknown, fallback: string): string {
  return err instanceof ApiError ? err.message : fallback;
}

export function usePlan(): PlanState {
  const [days, setDays] = useState<DaysValue>(DEFAULT_DAYS);
  const [minutes, setMinutes] = useState<MinutesValue>(DEFAULT_MINUTES);
  const [plan, setPlan] = useState<MealPlan | null>(null);
  const [inventory, setInventory] = useState<InventoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [demo, setDemo] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [revising, setRevising] = useState(false);
  const [reviseError, setReviseError] = useState<string | null>(null);
  const [diff, setDiff] = useState<PlanDiffState | null>(null);

  const loadInventory = useCallback(async (): Promise<void> => {
    const result = await fetchInventory('active');
    setInventory(result.data);
    setDemo((previous) => previous || result.demo);
  }, []);

  useEffect(() => {
    void (async () => {
      await loadInventory();
      setLoading(false);
    })();
  }, [loadInventory]);

  const generate = useCallback(async (): Promise<void> => {
    setLoading(true);
    setError(null);
    setDiff(null);
    try {
      const result = await loadPlan({
        days: Number(days),
        servings: SERVINGS,
        max_minutes: Number(minutes),
      });
      setPlan(result.data);
      setDemo((previous) => previous || result.demo);
      await loadInventory();
    } catch (err) {
      setError(messageOf(err, '生成饮食计划失败，请稍后重试'));
    } finally {
      setLoading(false);
    }
  }, [days, minutes, loadInventory]);

  /** §6.9：只改指令涉及的餐次；失败保留原计划，不做假改动 */
  const revise = useCallback(
    async (instruction: string): Promise<ReviseOutcome> => {
      const current = plan;
      if (!current) {
        return { ok: false, changed: [], learned: [], message: '还没有可调整的计划' };
      }
      setRevising(true);
      setReviseError(null);
      try {
        const revised = await reviseMealPlan(current.plan_id, instruction);
        setPlan({
          plan_id: revised.plan_id || current.plan_id,
          run_id: revised.run_id || current.run_id,
          days: revised.days,
          shopping: revised.shopping,
          coverage: revised.coverage,
          warnings: revised.warnings,
        });
        setDiff({ changed: revised.changed, warnings: revised.warnings });
        return { ok: true, changed: revised.changed, learned: revised.learned };
      } catch (err) {
        const message = messageOf(err, '调整失败，请稍后重试');
        // 保留原计划，只提示失败原因
        setReviseError(message);
        return { ok: false, changed: [], learned: [], message };
      } finally {
        setRevising(false);
      }
    },
    [plan],
  );

  const dismissDiff = useCallback((): void => {
    setDiff(null);
  }, []);

  return {
    days,
    minutes,
    plan,
    inventory,
    loading,
    demo,
    error,
    revising,
    reviseError,
    diff,
    setDays,
    setMinutes,
    generate,
    revise,
    dismissDiff,
  };
}
