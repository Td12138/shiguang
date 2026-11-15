/**
 * 业务端点（§6.1–§6.5、§6.7）：健康、拍照识别、库存、菜谱、统计、Agent trace。
 * 底座见 http.ts；计划与偏好见 client-plan.ts。
 */
import { jsonInit, request, UPLOAD_TIMEOUT_MS } from './http';
import type {
  AgentRun,
  ConsumeResult,
  CookSequence,
  CookSequenceRequest,
  CreateInventoryRequest,
  CreateInventoryResponse,
  DiscardReason,
  HealthResponse,
  InventoryItem,
  InventoryOperationResult,
  ReceiptResult,
  RecognitionResult,
  ReconcileApplyRequest,
  ReconcileApplyResult,
  ReconcileResult,
  StatsSummary,
  SuggestRequest,
  SuggestResponse,
  UpdateInventoryInput,
} from './types';

export { ApiError, BASE_URL } from './http';

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

/** §6.11 小票识别：同一张图上传入口，返回带 price/purchased_at 的清单 */
export function recognizeReceipt(file: File): Promise<ReceiptResult> {
  const form = new FormData();
  form.append('file', file);
  return request<ReceiptResult>(
    '/capture/receipt',
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

export function consumeInventory(id: string, grams?: number): Promise<ConsumeResult> {
  const body = typeof grams === 'number' ? { grams } : {};
  return request<ConsumeResult>(
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

/* ---------------------------------------------------------- §6.13 库存对账 */

export function recognizeReconcile(file: File): Promise<ReconcileResult> {
  const form = new FormData();
  form.append('file', file);
  return request<ReconcileResult>(
    '/inventory/reconcile',
    { method: 'POST', body: form },
    UPLOAD_TIMEOUT_MS,
  );
}

export function applyReconcile(body: ReconcileApplyRequest): Promise<ReconcileApplyResult> {
  return request<ReconcileApplyResult>('/inventory/reconcile/apply', jsonInit('POST', body));
}

/* ---------------------------------------------------------------- §6.5 统计 */

export function getStatsSummary(range = '30d'): Promise<StatsSummary> {
  return request<StatsSummary>(`/stats/summary?range=${encodeURIComponent(range)}`);
}

/* ------------------------------------------------------------ §6.7 Agent trace */

export function getAgentRun(runId: string): Promise<AgentRun> {
  return request<AgentRun>(`/agent/runs/${encodeURIComponent(runId)}`);
}

/* ------------------------------------------------------------ §6.12 备菜流水线 */

/** 多道菜并行排序要跑一次模型，给足时间 */
const SEQUENCE_TIMEOUT_MS = 60_000;

export function createCookSequence(body: CookSequenceRequest): Promise<CookSequence> {
  return request<CookSequence>('/cook/sequence', jsonInit('POST', body), SEQUENCE_TIMEOUT_MS);
}
