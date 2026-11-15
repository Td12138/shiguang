import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError, loadStats, streamWeeklyReport } from '@/lib/api';
import type { Citation, StatsSummary } from '@/lib/api';

/** 周报区间固定 30 天（契约 §6.6 无参数，服务端默认区间） */
const REPORT_RANGE = '30d';

export type ReportStatus = 'idle' | 'streaming' | 'done' | 'error';

export interface WeeklyReportState {
  status: ReportStatus;
  text: string;
  citations: Citation[];
  error: string | null;
  /** 失败回落用的统计摘要 */
  fallback: StatsSummary | null;
  fallbackDemo: boolean;
  start: () => Promise<void>;
}

export function useWeeklyReport(): WeeklyReportState {
  const [status, setStatus] = useState<ReportStatus>('idle');
  const [text, setText] = useState('');
  const [citations, setCitations] = useState<Citation[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [fallback, setFallback] = useState<StatsSummary | null>(null);
  const [fallbackDemo, setFallbackDemo] = useState(false);
  const started = useRef(false);

  const start = useCallback(async (): Promise<void> => {
    setStatus('streaming');
    setText('');
    setCitations([]);
    setError(null);
    setFallback(null);

    try {
      await streamWeeklyReport({
        onDelta: (chunk) => setText((previous) => previous + chunk),
        onCitations: (items) => setCitations(items),
        onDone: () => setStatus('done'),
      });
      setStatus((previous) => (previous === 'streaming' ? 'done' : previous));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '周报生成失败，请稍后重试');
      setStatus('error');
      const summary = await loadStats(REPORT_RANGE);
      setFallback(summary.data);
      setFallbackDemo(summary.demo);
    }
  }, []);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    void start();
  }, [start]);

  return { status, text, citations, error, fallback, fallbackDemo, start };
}
