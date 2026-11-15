import { useCallback, useEffect, useState } from 'react';
import { describeApiError, loadInventory, loadSuggestion } from '@/lib/api';
import type { InventoryItem, SuggestResponse } from '@/lib/api';
import { pickSuggestSeeds } from './selectors';

/** 建议条数（契约 §6.4 limit 默认 3） */
const SUGGEST_LIMIT = 3;
/** 时间上限：上班/上课回来的晚餐场景 */
const MAX_MINUTES = 30;

export interface DashboardState {
  inventory: InventoryItem[];
  suggestion: SuggestResponse | null;
  loading: boolean;
  /** 任一接口回落 mock 时为 true，页面显示「演示数据」提示条 */
  demo: boolean;
  /** 真实的 4xx/5xx 信息（不再伪装成演示数据） */
  error: string | null;
  reload: () => Promise<void>;
  /** 改数量/到期日后用后端返回的整条记录替换，不重启整页 */
  replaceItem: (item: InventoryItem) => void;
  /** 丢弃成功后从当前库存移除 */
  removeItem: (id: string) => void;
}

export function useDashboard(): DashboardState {
  const [inventory, setInventory] = useState<InventoryItem[]>([]);
  const [suggestion, setSuggestion] = useState<SuggestResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [demo, setDemo] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (): Promise<void> => {
    setLoading(true);
    setError(null);
    try {
      const inv = await loadInventory('active');
      const seeds = pickSuggestSeeds(inv.data);
      const sug = await loadSuggestion(seeds, SUGGEST_LIMIT, MAX_MINUTES);
      setInventory(inv.data);
      setSuggestion(sug.data);
      setDemo(inv.demo || sug.demo);
    } catch (err) {
      // 只有传输失败/5xx 会回样例；其余错误如实展示，避免把 401/413 说成「接口没有响应」
      setInventory([]);
      setSuggestion(null);
      setDemo(false);
      setError(describeApiError(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const replaceItem = useCallback((updated: InventoryItem): void => {
    setInventory((previous) =>
      previous.map((item) => (item.id === updated.id ? updated : item)),
    );
  }, []);

  const removeItem = useCallback((id: string): void => {
    setInventory((previous) => previous.filter((item) => item.id !== id));
  }, []);

  return { inventory, suggestion, loading, demo, error, reload: load, replaceItem, removeItem };
}
