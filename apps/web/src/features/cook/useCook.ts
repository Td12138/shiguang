import { useCallback, useEffect, useState } from 'react';
import { ApiError, consumeInventory, loadInventory as fetchInventory, loadSuggestion } from '@/lib/api';
import type { InventoryItem, RecipeRecommendation, SuggestResponse } from '@/lib/api';
import type { ConsumeLine } from './consume';

/** 建议条数上限（契约 §6.4 默认 3） */
const LIMIT = 3;
/** 单餐时间上限：下班/下课回来做饭 */
const MAX_MINUTES = 30;
/** 「临期」口径：3 天内到期（契约 §6.3 soon/urgent/expired） */
const URGENT_DAYS = 3;

export interface ConsumeOutcome {
  ok: boolean;
  consumed: string[];
  message?: string;
}

export interface CookState {
  inventory: InventoryItem[];
  loading: boolean;
  demo: boolean;
  selected: string[];
  suggestion: SuggestResponse | null;
  suggesting: boolean;
  error: string | null;
  consuming: boolean;
  doneIds: string[];
  toggle: (id: string) => void;
  selectExpiring: () => void;
  clearSelection: () => void;
  suggest: () => Promise<void>;
  consume: (recipe: RecipeRecommendation, chosen: ConsumeLine[]) => Promise<ConsumeOutcome>;
  reset: () => void;
}

function messageOf(err: unknown, fallback: string): string {
  return err instanceof ApiError ? err.message : fallback;
}

export function useCook(): CookState {
  const [inventory, setInventory] = useState<InventoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [demo, setDemo] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const [suggestion, setSuggestion] = useState<SuggestResponse | null>(null);
  const [suggesting, setSuggesting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [consuming, setConsuming] = useState(false);
  const [doneIds, setDoneIds] = useState<string[]>([]);

  const refresh = useCallback(async (keepSelection: boolean): Promise<void> => {
    setLoading(true);
    const result = await fetchInventory('active');
    setInventory(result.data);
    setDemo(result.demo);
    setSelected((previous) => {
      if (keepSelection) {
        const alive = previous.filter((id) => result.data.some((item) => item.id === id));
        return alive.length > 0 ? alive : result.data.filter((item) => item.days_left <= URGENT_DAYS).map((item) => item.id);
      }
      return result.data
        .filter((item) => item.days_left <= URGENT_DAYS)
        .map((item) => item.id);
    });
    setLoading(false);
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

  const suggest = useCallback(async (): Promise<void> => {
    setSuggesting(true);
    setError(null);
    try {
      const result = await loadSuggestion(selected, LIMIT, MAX_MINUTES);
      setSuggestion(result.data);
      setDemo((previous) => previous || result.demo);
    } catch (err) {
      setError(messageOf(err, '生成建议失败，请稍后重试'));
    } finally {
      setSuggesting(false);
    }
  }, [selected]);

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
          message: messageOf(err, '扣减库存失败，请稍后重试'),
        };
      } finally {
        setConsuming(false);
      }
    },
    [refresh],
  );

  const reset = useCallback((): void => {
    setSuggestion(null);
    setDoneIds([]);
    setError(null);
    void refresh(false);
  }, [refresh]);

  return {
    inventory,
    loading,
    demo,
    selected,
    suggestion,
    suggesting,
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
