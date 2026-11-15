/**
 * SSE 客户端（契约 §6.6 周报 / §6.15 计划与推荐流式）。
 * 支持 POST + AbortController：调用方取消时 fetch 直接中断，服务端随之停止。
 */
import { ApiError, BASE_URL } from './client';
import { stepFromEvent } from './types-stream';
import type {
  AgentStep,
  Citation,
  MealPlan,
  PlanRequest,
  StreamEvent,
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

/* ---------------------------------------------------------------- §6.6 周报 */

export interface WeeklyReportHandlers {
  onDelta?: (text: string) => void;
  onCitations?: (items: Citation[]) => void;
  onDone?: () => void;
}

function parseEvent(raw: string): WeeklyReportEvent | null {
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (typeof parsed !== 'object' || parsed === null) return null;
    const type = (parsed as Record<string, unknown>).type;
    if (type === 'delta' || type === 'citations' || type === 'done') {
      return parsed as WeeklyReportEvent;
    }
    return null;
  } catch {
    return null;
  }
}

/** 一个 SSE 事件块可能跨多个 data: 行 */
function handleChunk(chunk: string, handlers: WeeklyReportHandlers): void {
  const payload = chunk
    .split('\n')
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.slice('data:'.length).trim())
    .join('');
  if (!payload) return;

  const event = parseEvent(payload);
  if (!event) return;
  if (event.type === 'delta') handlers.onDelta?.(event.text);
  else if (event.type === 'citations') handlers.onCitations?.(event.items);
  else handlers.onDone?.();
}

export async function streamWeeklyReport(
  handlers: WeeklyReportHandlers,
  body: Record<string, unknown> = {},
): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`${BASE_URL}${API_PREFIX}${REPORT_PATH}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
      body: JSON.stringify(body),
    });
  } catch {
    throw new ApiError('network', '无法连接后端服务（127.0.0.1:8720）', 0);
  }
  if (!res.ok || !res.body) {
    throw new ApiError(`http_${res.status}`, `周报生成失败（HTTP ${res.status}）`, res.status);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split('\n\n');
    buffer = chunks.pop() ?? '';
    for (const chunk of chunks) handleChunk(chunk, handlers);
  }
  if (buffer.trim()) handleChunk(buffer, handlers);
}

/* ------------------------------------------------------------ §6.15 流式事件 */

export interface StreamHandlers<T> {
  onStep?: (step: AgentStep) => void;
  onDelta?: (text: string) => void;
  onResult?: (payload: T) => void;
  /** 后端主动发来的 error 事件（不是抛出的异常） */
  onError?: (error: ApiError) => void;
  onDone?: () => void;
}

function parseStreamEvent(raw: string): StreamEvent<unknown> | null {
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (typeof parsed !== 'object' || parsed === null) return null;
    const type = (parsed as Record<string, unknown>).type;
    if (type === 'step' || type === 'delta' || type === 'result' || type === 'error' || type === 'done') {
      return parsed as StreamEvent<unknown>;
    }
    return null;
  } catch {
    return null;
  }
}

function dispatch<T>(chunk: string, handlers: StreamHandlers<T>): void {
  const payload = chunk
    .split('\n')
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.slice('data:'.length).trim())
    .join('');
  if (!payload) return;

  const event = parseStreamEvent(payload);
  if (!event) return;
  switch (event.type) {
    case 'step':
      handlers.onStep?.(stepFromEvent(event));
      break;
    case 'delta':
      handlers.onDelta?.(event.text);
      break;
    case 'result':
      handlers.onResult?.(event.payload as T);
      break;
    case 'error':
      handlers.onError?.(new ApiError(event.code, event.message, 0));
      break;
    default:
      handlers.onDone?.();
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
      for (const chunk of chunks) dispatch(chunk, handlers);
    }
    if (buffer.trim()) dispatch(buffer, handlers);
  } catch (err) {
    if (isAbortError(err)) throw err;
    throw new ApiError('network', '流式连接中断，请重试', 0);
  }
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
