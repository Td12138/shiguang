import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError, describeApiError, isAbortError } from '@/lib/api';
import type { AgentStep, StreamHandlers } from '@/lib/api';
import { SLOW_HINT_MS, buildStreamSteps } from '@/lib/stream';

export interface StreamRunOptions<T> {
  /** 契约规定的固定步骤名（未到的会补成灰色占位） */
  stepNames: readonly string[];
  /** 实际发起流式请求，把 signal 透传给 fetch */
  run: (handlers: StreamHandlers<T>, signal: AbortSignal) => Promise<void>;
  onResult: (payload: T) => void;
  /** 网络/业务错误（用户取消不会走到这里） */
  onError: (error: ApiError) => void;
}

export interface StreamRunState {
  running: boolean;
  /** 已补齐占位的时间线（running / pending / ok…） */
  steps: AgentStep[];
  delta: string;
  /** 3 秒内没有任何 step 事件 */
  slow: boolean;
  start: <T>(options: StreamRunOptions<T>) => void;
  cancel: () => void;
}

/** 计划/推荐共用的流式状态机：step 事件点时间线，result 出结果，done 收尾，abort 取消 */
export function useStreamRun(): StreamRunState {
  const [running, setRunning] = useState(false);
  const [arrived, setArrived] = useState<AgentStep[]>([]);
  const [expected, setExpected] = useState<readonly string[]>([]);
  const [delta, setDelta] = useState('');
  const [slow, setSlow] = useState(false);
  const controllerRef = useRef<AbortController | null>(null);
  const slowTimer = useRef<number | null>(null);

  const clearSlow = useCallback((): void => {
    if (slowTimer.current !== null) {
      window.clearTimeout(slowTimer.current);
      slowTimer.current = null;
    }
  }, []);

  const stop = useCallback((): void => {
    clearSlow();
    setRunning(false);
    setSlow(false);
  }, [clearSlow]);

  useEffect(
    () => () => {
      controllerRef.current?.abort();
      clearSlow();
    },
    [clearSlow],
  );

  const start = useCallback(
    <T,>(options: StreamRunOptions<T>): void => {
      controllerRef.current?.abort();
      const controller = new AbortController();
      controllerRef.current = controller;

      setExpected(options.stepNames);
      setArrived([]);
      setDelta('');
      setSlow(false);
      setRunning(true);
      clearSlow();
      // 首字节/首个 step 迟迟不来时给一句提示，避免界面看起来卡死
      slowTimer.current = window.setTimeout(() => setSlow(true), SLOW_HINT_MS);

      void options
        .run(
          {
            onStep: (step) => {
              clearSlow();
              setSlow(false);
              setArrived((previous) => [
                ...previous.filter((item) => item.name !== step.name),
                step,
              ]);
            },
            onDelta: (text) => setDelta(text),
            onResult: (payload) => {
              stop();
              options.onResult(payload);
            },
            onError: (error) => {
              stop();
              options.onError(error);
            },
            // done 只负责收尾；result 通常已经在它之前到达
            onDone: stop,
          },
          controller.signal,
        )
        .catch((err: unknown) => {
          stop();
          if (isAbortError(err)) return;
          options.onError(
            err instanceof ApiError ? err : new ApiError('stream_failed', describeApiError(err), 0),
          );
        });
    },
    [clearSlow, stop],
  );

  const cancel = useCallback((): void => {
    controllerRef.current?.abort();
    controllerRef.current = null;
    stop();
  }, [stop]);

  return {
    running,
    steps: buildStreamSteps(expected, arrived),
    delta,
    slow,
    start,
    cancel,
  };
}
