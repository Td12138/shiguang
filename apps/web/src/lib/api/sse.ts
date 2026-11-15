/**
 * SSE 客户端（契约 §6.6 周报 / §6.15 计划与推荐流式）。
 * 统一走 streamPost：支持 POST + AbortController，调用方取消时 fetch 直接中断。
 */
import { ApiError, BASE_URL } from './client';
import { stepFromEvent } from './types-stream';
import type {
  AgentStep,
  Citation,
  MealPlan,
  PlanRequest,
  SuggestRequest,
  SuggestResponse,
  WeeklyReportEvent,
} from './types';

const API_PREFIX = '/api';
const REPORT_PATH = '/report/weekly';
const PLAN_STREAM_PATH = '/plan/meals/stream';
const SUGGEST_STREAM_PATH = '/recipes/suggest/stream';

/** 用户主动取消：调用方据此回到「未生成」，不当错误处理 */
export function isAbortError(err: unknown): boolean {
  return err instanceof DOMException && err.name === 'AbortError';
}

interface RawStreamEvent {
  type: string;
  [key: string]: unknown;
}

export interface StreamHandlers<T> {
  onStep?: (step: AgentStep) => void;
  onDelta?: (text: string) => void;
  onResult?: (payload: T) => void;
  /** 后端主动发来的 error 事件（不是抛出的异常） */
  onError?: (error: ApiError) => void;
  onDone?: () => void;
  /** 其它事件（如周报的 citations），由调用方自行解释 */
  onUnknown?: (event: RawStreamEvent) => void;
}

function parseEvent(raw: string): RawStreamEvent | null {
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (typeof parsed !== 'object' || parsed === null) return null;
    const type = (parsed as Record<string, unknown>).type;
    if (typeof type !== 'string') return null;
    return parsed as RawStreamEvent;
  } catch {
    return null;
  }
}

/** 一个 SSE 事件块可能跨多个 data: 行 */
function handleChunk<T>(chunk: string, handlers: StreamHandlers<T>): void {
  const payload = chunk
    .split('\n')
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.slice('data:'.length).trim())
    .join('');
  if (!payload) return;

  const event = parseEvent(payload);
  if (!event) return;
  switch (event.type) {
    case 'step':
      handlers.onStep?.(stepFromEvent(event as unknown as Parameters<typeof stepFromEvent>[0]));
      break;
    case 'delta':
      if (typeof event.text === 'string') handlers.onDelta?.(event.text);
      break;
    case 'result':
      handlers.onResult?.(event.payload as T);
      break;
    case 'error':
      handlers.onError?.(
        new ApiError(
          typeof event.code === 'string' ? event.code : 'stream_error',
          typeof event.message === 'string' ? event.message : '流式请求失败',
          0,
        ),
      );
      break;
    case 'done':
      handlers.onDone?.();
      break;
    default:
      handlers.onUnknown?.(event);
  }
}

/** 通用 POST + SSE：调用方给 AbortSignal，取消时抛 AbortError */
export async function streamPost<T>(
  path: string,
  body: unknown,
  handlers: StreamHandlers<T>,
  signal?: AbortSignal,
): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`${BASE_URL}${API_PREFIX}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
      body: JSON.stringify(body),
      ...(signal ? { signal } : {}),
    });
  } catch (err) {
    if (isAbortError(err)) throw err;
    throw new ApiError('network', '无法连接后端服务（127.0.0.1:8720）', 0);
  }
  if (!res.ok || !res.body) {
    throw new ApiError(`http_${res.status}`, `流式接口失败（HTTP ${res.status}）`, res.status);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const chunks = buffer.split('\n\n');
      buffer = chunks.pop() ?? '';
      for (const chunk of chunks) handleChunk(chunk, handlers);
    }
    if (buffer.trim()) handleChunk(buffer, handlers);
  } catch (err) {
    if (isAbortError(err)) throw err;
    throw new ApiError('network', '流式连接中断，请重试', 0);
  }
}

/* ---------------------------------------------------------------- §6.6 周报 */

export interface WeeklyReportHandlers {
  onDelta?: (text: string) => void;
  onCitations?: (items: Citation[]) => void;
  onDone?: () => void;
}

export async function streamWeeklyReport(
  handlers: WeeklyReportHandlers,
  body: Record<string, unknown> = {},
  signal?: AbortSignal,
): Promise<void> {
  await streamPost<WeeklyReportEvent>(REPORT_PATH, body, {
    ...(handlers.onDelta ? { onDelta: handlers.onDelta } : {}),
    ...(handlers.onDone ? { onDone: handlers.onDone } : {}),
    onUnknown: (event) => {
      if (event.type === 'citations' && Array.isArray(event.items)) {
        handlers.onCitations?.(event.items as Citation[]);
      }
    },
  }, signal);
}

/* ------------------------------------------------------- §6.15 业务包装函数 */

export function streamPlan(
  body: PlanRequest,
  handlers: StreamHandlers<MealPlan>,
  signal?: AbortSignal,
): Promise<void> {
  return streamPost<MealPlan>(PLAN_STREAM_PATH, body, handlers, signal);
}

export function streamSuggest(
  body: SuggestRequest,
  handlers: StreamHandlers<SuggestResponse>,
  signal?: AbortSignal,
): Promise<void> {
  return streamPost<SuggestResponse>(SUGGEST_STREAM_PATH, body, handlers, signal);
}
