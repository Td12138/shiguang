import { useCallback, useEffect, useState } from 'react';
import { loadInventory, loadSuggestion } from '@/lib/api';
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
  reload: () => Promise<void>;
}

export function useDashboard(): DashboardState {
  const [inventory, setInventory] = useState<InventoryItem[]>([]);
  const [suggestion, setSuggestion] = useState<SuggestResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [demo, setDemo] = useState(false);

  const load = useCallback(async (): Promise<void> => {
    setLoading(true);
    try {
      const inv = await loadInventory('active');
      const seeds = pickSuggestSeeds(inv.data);
      const sug = await loadSuggestion(seeds, SUGGEST_LIMIT, MAX_MINUTES);
      setInventory(inv.data);
      setSuggestion(sug.data);
      setDemo(inv.demo || sug.demo);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return { inventory, suggestion, loading, demo, reload: load };
}
