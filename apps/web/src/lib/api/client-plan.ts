/**
 * 饮食计划迭代（§6.9）与用户偏好（§6.10）。
 * 与 client.ts 拆开，避免单文件超过 200 行。
 */
import { PLAN_TIMEOUT_MS, jsonInit, request } from './http';
import type { MealPlan, PlanRequest, RevisedPlan } from './types';
import type { Preference, PreferenceKind, PreferenceList } from './types-plan';

export function createMealPlan(body: PlanRequest): Promise<MealPlan> {
  return request<MealPlan>('/plan/meals', jsonInit('POST', body), PLAN_TIMEOUT_MS);
}

/** 在同一个 plan 上迭代：只改指令涉及的餐次，返回 changed diff */
export function reviseMealPlan(planId: string, instruction: string): Promise<RevisedPlan> {
  return request<RevisedPlan>(
    `/plan/meals/${encodeURIComponent(planId)}/revise`,
    jsonInit('POST', { instruction }),
    PLAN_TIMEOUT_MS,
  );
}

export function listPreferences(): Promise<PreferenceList> {
  return request<PreferenceList>('/preferences');
}

export interface CreatePreferenceInput {
  text: string;
  kind: PreferenceKind;
}

export function createPreference(body: CreatePreferenceInput): Promise<Preference> {
  return request<Preference>('/preferences', jsonInit('POST', body));
}

/** 用户删除错误推断：契约 §6.10 的可控性底线 */
export function deletePreference(id: string): Promise<void> {
  return request<void>(`/preferences/${encodeURIComponent(id)}`, { method: 'DELETE' });
}
