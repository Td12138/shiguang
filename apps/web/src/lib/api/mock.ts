/**
 * 演示数据降级层。
 * 后端没起时不让页面白屏：捕获 ApiError 后返回 mock，并把 demo=true 传出去，
 * 页面据此渲染「演示数据」提示条 —— 不静默假装真实数据（契约 §10.5）。
 * 数据本体在 fixtures.ts / fixtures-recipes.ts。
 */
import {
  getAgentRun,
  getStatsSummary,
  listInventory,
  recognizeReconcile,
  suggestRecipes,
} from './client';
import { createMealPlan, listPreferences } from './client-plan';
import { MOCK_AGENT_RUN, MOCK_INVENTORY } from './fixtures';
import { MOCK_PLAN } from './fixtures-plan';
import { MOCK_PREFERENCES } from './fixtures-preferences';
import { MOCK_RECONCILE } from './fixtures-reconcile';
import { MOCK_STATS, MOCK_SUGGESTION } from './fixtures-recipes';
import type {
  AgentRun,
  InventoryItem,
  MealPlan,
  PlanRequest,
  PreferenceList,
  ReconcileResult,
  Sourced,
  StatsSummary,
  SuggestResponse,
} from './types';

export { MOCK_AGENT_RUN, MOCK_INVENTORY, MOCK_RECOGNITION, MOCK_RUN_ID } from './fixtures';
export { MOCK_PLAN, MOCK_PLAN_RUN_ID } from './fixtures-plan';
export { MOCK_PREFERENCES } from './fixtures-preferences';
export { MOCK_RECEIPT } from './fixtures-receipt';
export { MOCK_RECONCILE } from './fixtures-reconcile';
export { MOCK_STATS, MOCK_SUGGESTION } from './fixtures-recipes';

/** 真实请求失败 → 回落 mock，并标记 demo；成功路径原样返回 */
export async function withDemoFallback<T>(
  call: () => Promise<T>,
  fallback: () => T,
): Promise<Sourced<T>> {
  try {
    return { data: await call(), demo: false };
  } catch {
    return { data: fallback(), demo: true };
  }
}

export function loadInventory(
  status: 'active' | 'consumed' | 'discarded' = 'active',
): Promise<Sourced<InventoryItem[]>> {
  return withDemoFallback<InventoryItem[]>(
    () => listInventory(status),
    () => MOCK_INVENTORY,
  );
}

export function loadSuggestion(
  useIds: string[],
  limit = 3,
  maxMinutes = 30,
): Promise<Sourced<SuggestResponse>> {
  return withDemoFallback<SuggestResponse>(
    () => suggestRecipes({ use: useIds, limit, max_minutes: maxMinutes }),
    () => MOCK_SUGGESTION,
  );
}

/** runId 为空（演示数据）或请求失败时，都回落样例步骤 */
export function loadAgentRun(runId: string | null): Promise<Sourced<AgentRun>> {
  return withDemoFallback<AgentRun>(
    () => (runId ? getAgentRun(runId) : Promise.reject(new Error('缺少 run_id'))),
    () => MOCK_AGENT_RUN,
  );
}

export function loadStats(range = '30d'): Promise<Sourced<StatsSummary>> {
  return withDemoFallback<StatsSummary>(
    () => getStatsSummary(range),
    () => MOCK_STATS,
  );
}

/** §6.8：后端 /api/plan/meals 未就绪时回落样例计划 */
export function loadPlan(body: PlanRequest): Promise<Sourced<MealPlan>> {
  return withDemoFallback<MealPlan>(
    () => createMealPlan(body),
    () => MOCK_PLAN,
  );
}

/**
 * §6.10 偏好列表：读失败回样例（面板标「演示数据」）。
 * 写操作（新增/删除）不做 mock 回落——写入不能假装成功。
 */
export function loadPreferences(): Promise<Sourced<PreferenceList>> {
  return withDemoFallback<PreferenceList>(
    () => listPreferences(),
    () => MOCK_PREFERENCES,
  );
}

/**
 * §6.13 对账识别：后端不通时回样例并标记 demo（页面必须显示「演示数据」）。
 * 注意 apply 从不回落：改数据必须真的成功，否则保留用户选择。
 */
export function loadReconcile(file: File): Promise<Sourced<ReconcileResult>> {
  return withDemoFallback<ReconcileResult>(
    () => recognizeReconcile(file),
    () => MOCK_RECONCILE,
  );
}
