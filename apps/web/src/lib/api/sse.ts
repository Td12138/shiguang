/** 周报 SSE 客户端：逐块回调，供 features/report 使用（契约 §6.6） */
import { ApiError, BASE_URL } from './client';
import type { Citation, WeeklyReportEvent } from './types';

const API_PREFIX = '/api';
const REPORT_PATH = '/report/weekly';

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
