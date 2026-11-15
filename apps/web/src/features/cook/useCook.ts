import { useCallback, useEffect, useState } from 'react';
import {
  consumeInventory,
  describeApiError,
  isTransportError,
  loadInventory as fetchInventory,
  loadSuggestion,
  streamSuggest,
} from '@/lib/api';
import type {
  ApiError,
  InventoryItem,
  RecipeRecommendation,
  SuggestRequest,
  SuggestResponse,
} from '@/lib/api';
import { SUGGEST_STEP_NAMES } from '@/lib/stream';
import { useStreamRun } from '@/features/stream/useStreamRun';
import type { ConsumeLine } from './consume';
import type { ConsumeOutcome, CookState } from './cookTypes';

export type { ConsumeOutcome, CookState } from './cookTypes';

/** 建议条数上限（契约 §6.4 默认 3） */
const LIMIT = 3;
/** 单餐时间上限：下班/下课回来做饭 */
const MAX_MINUTES = 30;
/** 「临期」口径：3 天内到期（契约 §6.3 soon/urgent/expired） */
const URGENT_DAYS = 3;

export function useCook(): CookState {
  const [inventory, setInventory] = useState<InventoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [demo, setDemo] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const [suggestion, setSuggestion] = useState<SuggestResponse | null>(null);
  const stream = useStreamRun();
  const [error, setError] = useState<string | null>(null);
  const [consuming, setConsuming] = useState(false);
  const [doneIds, setDoneIds] = useState<string[]>([]);

  const refresh = useCallback(async (keepSelection: boolean): Promise<void> => {
    setLoading(true);
    try {
      const result = await fetchInventory('active');
      setInventory(result.data);
      setDemo(result.demo);
      setSelected((previous) => {
        if (keepSelection) {
          const alive = previous.filter((id) => result.data.some((item) => item.id === id));
          return alive.length > 0
            ? alive
            : result.data.filter((item) => item.days_left <= URGENT_DAYS).map((item) => item.id);
        }
        return result.data
          .filter((item) => item.days_left <= URGENT_DAYS)
          .map((item) => item.id);
      });
    } catch (err) {
      setInventory([]);
      setDemo(false);
      setError(describeApiError(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh(false);
  }, [refresh]);

  const toggle = useCallback((id: string): void => {
    setSelected((previous) =>
      previous.includes(id) ? previous.filter((item) => item !== id) : [...previous, id],
    );
  }, []);

  const selectExpiring = useCallback((): void => {
    setSelected(inventory.filter((item) => item.days_left <= URGENT_DAYS).map((item) => item.id));
  }, [inventory]);

  const clearSelection = useCallback((): void => {
    setSelected([]);
  }, []);

  /** 流式失败时退回非流式：后端不通则 loadSuggestion 会回样例并标 demo */
  const recoverFromStreamError = useCallback(
    async (err: ApiError, body: SuggestRequest): Promise<void> => {
      if (!isTransportError(err)) {
        setError(describeApiError(err));
        return;
      }
      try {
        const fallback = await loadSuggestion(
          body.use,
          body.limit ?? LIMIT,
          body.max_minutes ?? MAX_MINUTES,
        );
        setSuggestion(fallback.data);
        setDemo((previous) => previous || fallback.demo);
      } catch (fallbackErr) {
        setError(describeApiError(fallbackErr));
      }
    },
    [],
  );

  const suggest = useCallback(async (): Promise<void> => {
    const body: SuggestRequest = { use: selected, limit: LIMIT, max_minutes: MAX_MINUTES };
    setError(null);
    setSuggestion(null);
    stream.start<SuggestResponse>({
      stepNames: SUGGEST_STEP_NAMES,
      run: (handlers, signal) => streamSuggest(body, handlers, signal),
      onResult: setSuggestion,
      onError: (err) => {
        void recoverFromStreamError(err, body);
      },
    });
  }, [selected, stream, recoverFromStreamError]);

  const cancelSuggest = useCallback((): void => {
    stream.cancel();
    setSuggestion(null);
  }, [stream]);

  const consume = useCallback(
    async (recipe: RecipeRecommendation, chosen: ConsumeLine[]): Promise<ConsumeOutcome> => {
      const fromRecipe = (recipe.uses ?? [])
        .map((use) => use.inventory_id)
        .filter((id): id is string => Boolean(id));
      const lines: ConsumeLine[] =
        fromRecipe.length > 0 ? fromRecipe.map((id) => ({ id })) : chosen;
      if (lines.length === 0) {
        return { ok: false, consumed: [], message: '先勾选这道菜用掉了哪些食材' };
      }

      setConsuming(true);
      const consumed: string[] = [];
      try {
        for (const line of lines) {
          await consumeInventory(line.id, line.grams);
          consumed.push(line.id);
        }
        setDoneIds((previous) => [...previous, recipe.recipe_id]);
        await refresh(true);
        return { ok: true, consumed };
      } catch (err) {
        await refresh(true);
        return {
          ok: false,
          consumed,
          message: describeApiError(err),
        };
      } finally {
        setConsuming(false);
      }
    },
    [refresh],
  );

  const reset = useCallback((): void => {
    stream.cancel();
    setSuggestion(null);
    setDoneIds([]);
    setError(null);
    void refresh(false);
  }, [refresh, stream]);

  return {
    inventory,
    loading,
    demo,
    selected,
    suggestion,
    suggesting: stream.running,
    streamSteps: stream.steps,
    streamDelta: stream.delta,
    streamSlow: stream.slow,
    cancelSuggest,
    error,
    consuming,
    doneIds,
    toggle,
    selectExpiring,
    clearSelection,
    suggest,
    consume,
    reset,
  };
}
