import { useCallback, useEffect, useState } from 'react';
import {
  describeApiError,
  isTransportError,
  loadInventory as fetchInventory,
  loadPlan,
  reviseMealPlan,
  streamPlan,
} from '@/lib/api';
import type { ApiError, InventoryItem, MealPlan, PlanRequest } from '@/lib/api';
import { PLAN_STEP_NAMES } from '@/lib/stream';
import type { DaysValue, MinutesValue, PlanState, ReviseOutcome } from './planTypes';
import { useStreamRun } from '@/features/stream/useStreamRun';
import type { PlanDiffState } from './PlanDiff';

export { DAY_OPTIONS, MINUTES_OPTIONS } from './planTypes';
export type { DaysValue, MinutesValue, PlanState, ReviseOutcome } from './planTypes';

const DEFAULT_DAYS: DaysValue = '3';
const DEFAULT_MINUTES: MinutesValue = '30';
/** 暂不支持多人：单人或两人份都按 1 人份配餐，页面上写明 */
const SERVINGS = 1;

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
  const stream = useStreamRun();

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

  /** 流式失败时退回非流式：后端不通则 loadPlan 会回样例并标 demo */
  const recoverFromStreamError = useCallback(
    async (err: ApiError, body: PlanRequest): Promise<void> => {
      // 传输失败、5xx，或后端还没上线流式端点（404/405）都退回非流式
      const streamUnavailable =
        isTransportError(err) || err.status === 404 || err.status === 405;
      if (!streamUnavailable) {
        setError(describeApiError(err));
        return;
      }
      try {
        const fallback = await loadPlan(body);
        setPlan(fallback.data);
        setDemo((previous) => previous || fallback.demo);
      } catch (fallbackErr) {
        setError(describeApiError(fallbackErr));
      }
    },
    [],
  );

  const generate = useCallback((): void => {
    const body: PlanRequest = {
      days: Number(days),
      servings: SERVINGS,
      max_minutes: Number(minutes),
    };
    setError(null);
    setDiff(null);
    setPlan(null);
    stream.start<MealPlan>({
      stepNames: PLAN_STEP_NAMES,
      run: (handlers, signal) => streamPlan(body, handlers, signal),
      onResult: (payload) => {
        setPlan(payload);
        void loadInventory();
      },
      onError: (err) => {
        void recoverFromStreamError(err, body);
      },
    });
  }, [days, minutes, loadInventory, stream, recoverFromStreamError]);

  /** 取消后回到「未生成」状态，不留半成品 */
  const cancelGenerate = useCallback((): void => {
    stream.cancel();
    setPlan(null);
    setError(null);
  }, [stream]);

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
        const message = describeApiError(err);
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
    streaming: stream.running,
    streamSteps: stream.steps,
    streamDelta: stream.delta,
    streamSlow: stream.slow,
    cancelGenerate,
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
