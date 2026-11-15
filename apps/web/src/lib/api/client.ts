/**
 * fetch 封装：baseURL 为空（dev 走 Vite 代理 /api → 127.0.0.1:8720），
 * 统一超时、错误归一化（全部抛 ApiError，页面只需判断 code）。
 */
import type {
  AgentRun,
  ApiErrorBody,
  CreateInventoryRequest,
  CreateInventoryResponse,
  DiscardReason,
  HealthResponse,
  InventoryItem,
  InventoryOperationResult,
  RecognitionResult,
  StatsSummary,
  SuggestRequest,
  SuggestResponse,
  UpdateInventoryInput,
} from './types';

/** 留空即同源请求，交给 vite.config.ts 的 proxy */
export const BASE_URL = '';
const API_PREFIX = '/api';

/** 普通请求超时 */
const DEFAULT_TIMEOUT_MS = 20_000;
/** 图片上传超时（VLM 慢） */
const UPLOAD_TIMEOUT_MS = 60_000;

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly detail: string | undefined;

  constructor(code: string, message: string, status = 0, detail?: string) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
    this.detail = detail;
  }
}

function isErrorBody(value: unknown): value is ApiErrorBody {
  if (typeof value !== 'object' || value === null) return false;
  const record = value as Record<string, unknown>;
  return typeof record.code === 'string' && typeof record.message === 'string';
}

async function safeJson(res: Response): Promise<unknown> {
  try {
    return (await res.json()) as unknown;
  } catch {
    return null;
  }
}

function normalizeError(err: unknown): ApiError {
  if (err instanceof ApiError) return err;
  if (err instanceof DOMException && err.name === 'AbortError') {
    return new ApiError('timeout', '请求超时，请确认后端服务已启动', 0);
  }
  if (err instanceof Error) {
    return new ApiError('network', '无法连接后端服务（127.0.0.1:8720）', 0);
  }
  return new ApiError('unknown', '未知错误', 0);
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  timeoutMs = DEFAULT_TIMEOUT_MS,
): Promise<T> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${BASE_URL}${API_PREFIX}${path}`, {
      ...init,
      signal: controller.signal,
      headers: { Accept: 'application/json', ...init.headers },
    });
    if (!res.ok) {
      const body = await safeJson(res);
      if (isErrorBody(body)) {
        throw new ApiError(body.code, body.message, res.status, body.detail);
      }
      throw new ApiError(`http_${res.status}`, `请求失败（HTTP ${res.status}）`, res.status);
    }
    if (res.status === 204) return undefined as T;
    return (await res.json()) as T;
  } catch (err) {
    throw normalizeError(err);
  } finally {
    window.clearTimeout(timer);
  }
}

function jsonInit(method: string, body: unknown): RequestInit {
  return {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  };
}

/* ---------------------------------------------------------------- §6.1 健康 */

export function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>('/health');
}

/* ------------------------------------------------------------ §6.2 拍照识别 */

export function recognizeImage(file: File): Promise<RecognitionResult> {
  const form = new FormData();
  form.append('file', file);
  return request<RecognitionResult>(
    '/capture/recognize',
    { method: 'POST', body: form },
    UPLOAD_TIMEOUT_MS,
  );
}

/* ---------------------------------------------------------------- §6.3 库存 */

export type InventoryStatus = 'active' | 'consumed' | 'discarded';

export function listInventory(status: InventoryStatus = 'active'): Promise<InventoryItem[]> {
  return request<InventoryItem[]>(`/inventory?status=${status}`);
}

export function createInventory(body: CreateInventoryRequest): Promise<CreateInventoryResponse> {
  return request<CreateInventoryResponse>('/inventory', jsonInit('POST', body));
}

export function updateInventory(
  id: string,
  patch: UpdateInventoryInput,
): Promise<InventoryItem> {
  return request<InventoryItem>(`/inventory/${encodeURIComponent(id)}`, jsonInit('PATCH', patch));
}

export function consumeInventory(
  id: string,
  grams?: number,
): Promise<InventoryOperationResult> {
  const body = typeof grams === 'number' ? { grams } : {};
  return request<InventoryOperationResult>(
    `/inventory/${encodeURIComponent(id)}/consume`,
    jsonInit('POST', body),
  );
}

export function discardInventory(
  id: string,
  reason: DiscardReason,
  grams?: number,
): Promise<InventoryOperationResult> {
  const body = typeof grams === 'number' ? { reason, grams } : { reason };
  return request<InventoryOperationResult>(
    `/inventory/${encodeURIComponent(id)}/discard`,
    jsonInit('POST', body),
  );
}

/* ---------------------------------------------------------------- §6.4 菜谱 */

export function suggestRecipes(body: SuggestRequest): Promise<SuggestResponse> {
  return request<SuggestResponse>('/recipes/suggest', jsonInit('POST', body));
}

/* ---------------------------------------------------------------- §6.5 统计 */

export function getStatsSummary(range = '30d'): Promise<StatsSummary> {
  return request<StatsSummary>(`/stats/summary?range=${encodeURIComponent(range)}`);
}

/* ------------------------------------------------------------ §6.7 Agent trace */

export function getAgentRun(runId: string): Promise<AgentRun> {
  return request<AgentRun>(`/agent/runs/${encodeURIComponent(runId)}`);
}

/* 周报 SSE 见 sse.ts：request() 不适合流式响应 */
