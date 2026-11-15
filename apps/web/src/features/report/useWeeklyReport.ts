import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ApiError,
  describeApiError,
  isAbortError,
  loadStats,
  streamWeeklyReport,
} from '@/lib/api';
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
  const controllerRef = useRef<AbortController | null>(null);
  /** 流进行中的同步锁：按钮 disabled 之外再兜一层，防双击开两条流 */
  const runningRef = useRef(false);

  const start = useCallback(async (): Promise<void> => {
    if (runningRef.current) return;
    runningRef.current = true;
    // 重新生成前先断开上一条流，避免两次 delta 交错
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;

    setStatus('streaming');
    setText('');
    setCitations([]);
    setError(null);
    setFallback(null);

    let sawDone = false;
    try {
      await streamWeeklyReport(
        {
          onDelta: (chunk) => setText((previous) => previous + chunk),
          onCitations: (items) => setCitations(items),
          onDone: () => {
            sawDone = true;
          },
        },
        {},
        controller.signal,
      );
      // sse 层已把「读完但没终态」当断流抛出；这里再兜一层，避免半截正文被当成成功
      if (!sawDone) {
        throw new ApiError('stream_incomplete', '流式连接提前结束，没有收到完成标记', 0);
      }
      setStatus('done');
    } catch (err) {
      if (isAbortError(err)) return;
      setError(describeApiError(err));
      setStatus('error');
      try {
        const summary = await loadStats(REPORT_RANGE);
        setFallback(summary.data);
        setFallbackDemo(summary.demo);
      } catch {
        // 连兜底统计都取不到：保留错误提示，不硬凑数字
        setFallback(null);
        setFallbackDemo(false);
      }
    } finally {
      if (controllerRef.current === controller) controllerRef.current = null;
      runningRef.current = false;
    }
  }, []);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    void start();
  }, [start]);

  return { status, text, citations, error, fallback, fallbackDemo, start };
}
