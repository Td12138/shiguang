/**
 * 演示数据降级层。
 * 后端没起时不让页面白屏：捕获 ApiError 后返回 mock，并把 demo=true 传出去，
 * 页面据此渲染「演示数据」提示条 —— 不静默假装真实数据（契约 §10.5）。
 * 数据本体在 fixtures.ts / fixtures-recipes.ts。
 */
import { getAgentRun, getStatsSummary, listInventory, suggestRecipes } from './client';
import { MOCK_AGENT_RUN, MOCK_INVENTORY } from './fixtures';
import { MOCK_STATS, MOCK_SUGGESTION } from './fixtures-recipes';
import type { AgentRun, InventoryItem, Sourced, StatsSummary, SuggestResponse } from './types';

export { MOCK_AGENT_RUN, MOCK_INVENTORY, MOCK_RECOGNITION, MOCK_RUN_ID } from './fixtures';
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
