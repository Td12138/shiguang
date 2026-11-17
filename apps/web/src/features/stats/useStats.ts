import { useCallback, useEffect, useState } from 'react';
import { describeApiError, loadStats } from '@/lib/api';
import type { StatsSummary } from '@/lib/api';

export const RANGE_OPTIONS = [
  { value: '7d', label: '近 7 天' },
  { value: '30d', label: '近 30 天' },
  { value: 'all', label: '全部' },
] as const;

export type RangeValue = (typeof RANGE_OPTIONS)[number]['value'];

/** 区间代码 → 人话（页面文案不该露 "30d" 这种内部口径） */
export function rangeLabel(value: string): string {
  return RANGE_OPTIONS.find((option) => option.value === value)?.label ?? value;
}

const DEFAULT_RANGE: RangeValue = '30d';

export interface StatsState {
  range: RangeValue;
  data: StatsSummary | null;
  loading: boolean;
  demo: boolean;
  error: string | null;
  setRange: (value: RangeValue) => void;
  reload: () => Promise<void>;
}

export function useStats(): StatsState {
  const [range, setRange] = useState<RangeValue>(DEFAULT_RANGE);
  const [data, setData] = useState<StatsSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [demo, setDemo] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (value: RangeValue): Promise<void> => {
    setLoading(true);
    setError(null);
    try {
      const result = await loadStats(value);
      setData(result.data);
      setDemo(result.demo);
    } catch (err) {
      // loadStats 只在传输失败/5xx 回落样例；4xx 会抛出来如实提示
      setData(null);
      setDemo(false);
      setError(describeApiError(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(range);
  }, [load, range]);

  return {
    range,
    data,
    loading,
    demo,
    error,
    setRange,
    reload: () => load(range),
  };
}
