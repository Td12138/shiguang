import { useCallback, useState } from 'react';
import { createCookSequence, describeApiError } from '@/lib/api';
import type { CookSequence } from '@/lib/api';
import { nowHhMm } from '@/lib/format';

/** 契约 §6.12 后端上限 6 道 */
export const MAX_SEQUENCE_RECIPES = 6;

export type PickResult = 'added' | 'removed' | 'limit';

export interface CookSequenceState {
  picked: string[];
  canPickMore: boolean;
  togglePick: (recipeId: string) => PickResult;
  /** 生成时间轴；失败保留界面并给出原因 */
  run: () => Promise<boolean>;
  sequence: CookSequence | null;
  loading: boolean;
  error: string | null;
  /** 换方案 / 清空选择时调用 */
  reset: () => void;
  clearError: () => void;
}

export function useCookSequence(): CookSequenceState {
  const [picked, setPicked] = useState<string[]>([]);
  const [sequence, setSequence] = useState<CookSequence | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const togglePick = useCallback(
    (recipeId: string): PickResult => {
      if (picked.includes(recipeId)) {
        setPicked(picked.filter((id) => id !== recipeId));
        return 'removed';
      }
      if (picked.length >= MAX_SEQUENCE_RECIPES) return 'limit';
      setPicked([...picked, recipeId]);
      return 'added';
    },
    [picked],
  );

  const run = useCallback(async (): Promise<boolean> => {
    if (picked.length === 0) {
      setError('先加入 1–6 道菜再生成时间轴');
      return false;
    }
    setLoading(true);
    setError(null);
    try {
      const result = await createCookSequence({ recipe_ids: picked, start_at: nowHhMm() });
      if (result.steps.length === 0) {
        setError('后端没有排出可用步骤，换几道菜再试');
        return false;
      }
      setSequence(result);
      return true;
    } catch (err) {
      setError(describeApiError(err));
      return false;
    } finally {
      setLoading(false);
    }
  }, [picked]);

  const reset = useCallback((): void => {
    setPicked([]);
    setSequence(null);
    setError(null);
  }, []);

  const clearError = useCallback((): void => {
    setError(null);
  }, []);

  return {
    picked,
    canPickMore: picked.length < MAX_SEQUENCE_RECIPES,
    togglePick,
    run,
    sequence,
    loading,
    error,
    reset,
    clearError,
  };
}
