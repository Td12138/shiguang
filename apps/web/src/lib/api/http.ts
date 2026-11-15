/**
 * HTTP 底座：baseURL 为空（dev 走 Vite 代理 /api → 127.0.0.1:8720），
 * 统一超时与错误归一化。业务端点分在 client.ts / client-plan.ts。
 */
export const BASE_URL = '';
export const API_PREFIX = '/api';

/** 普通请求超时 */
export const DEFAULT_TIMEOUT_MS = 20_000;
/** 图片上传超时（VLM 慢） */
export const UPLOAD_TIMEOUT_MS = 60_000;
/** 计划生成 / 改计划要跑多步 Agent */
export const PLAN_TIMEOUT_MS = 90_000;

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

function isErrorBody(value: unknown): value is { code: string; message: string; detail?: string } {
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

export async function request<T>(
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

export function jsonInit(method: string, body: unknown): RequestInit {
  return {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  };
}
