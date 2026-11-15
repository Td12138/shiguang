import { useCallback, useEffect, useState } from 'react';
import { ApiError, loadInventory as fetchInventory, loadPlan } from '@/lib/api';
import type { InventoryItem, MealPlan } from '@/lib/api';

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

export interface PlanState {
  days: DaysValue;
  minutes: MinutesValue;
  plan: MealPlan | null;
  inventory: InventoryItem[];
  loading: boolean;
  demo: boolean;
  error: string | null;
  setDays: (value: DaysValue) => void;
  setMinutes: (value: MinutesValue) => void;
  generate: () => Promise<void>;
}

function messageOf(err: unknown): string {
  return err instanceof ApiError ? err.message : '生成饮食计划失败，请稍后重试';
}

export function usePlan(): PlanState {
  const [days, setDays] = useState<DaysValue>(DEFAULT_DAYS);
  const [minutes, setMinutes] = useState<MinutesValue>(DEFAULT_MINUTES);
  const [plan, setPlan] = useState<MealPlan | null>(null);
  const [inventory, setInventory] = useState<InventoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [demo, setDemo] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
      setError(messageOf(err));
    } finally {
      setLoading(false);
    }
  }, [days, minutes, loadInventory]);

  return { days, minutes, plan, inventory, loading, demo, error, setDays, setMinutes, generate };
}
