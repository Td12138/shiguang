/**
 * §6.9 对话改计划 + §6.10 用户偏好 的类型。
 * 与 types-ai.ts 拆开，保持每个文件在 200 行内。
 */
import type { MealPlan } from './types-ai';

export interface PlanChange {
  /** YYYY-MM-DD，与 meals[].date 一致 */
  date: string;
  slot: string;
  /** 原菜名；新增餐次时为 null（后端 plan.py 会返回 null） */
  from: string | null;
  /** 新菜名；只删不补时为 null */
  to: string | null;
  reason: string;
}

export type PreferenceKind = 'avoid' | 'like' | 'time' | 'portion' | 'health';

export type PreferenceSource = 'dialog' | 'manual';

/** 对话里推断出来的偏好，前端用它做「已记住 + 撤销」 */
export interface LearnedPreference {
  id: string;
  text: string;
  kind: PreferenceKind;
}

export interface Preference {
  id: string;
  text: string;
  kind: PreferenceKind;
  source: PreferenceSource;
  /** 0–1；< 0.6 不展示为已生效（契约 §6.10） */
  confidence: number;
  created_at: string;
}

export interface PreferenceList {
  items: Preference[];
}

/** revize 返回体 = 新计划 + diff + 新学到的偏好 */
export interface RevisedPlan extends MealPlan {
  changed: PlanChange[];
  learned: LearnedPreference[];
}

/** 偏好类型的中文标签（面板分组与下拉共用） */
export const PREFERENCE_KIND_LABELS: Record<PreferenceKind, string> = {
  avoid: '忌口',
  like: '喜好',
  time: '时间',
  portion: '份量',
  health: '健康',
};

/** 分组顺序：硬约束在前 */
export const PREFERENCE_KIND_ORDER: PreferenceKind[] = [
  'avoid',
  'like',
  'time',
  'portion',
  'health',
];

/** 低于该置信度只在提示里出现，不算「已生效」 */
export const PREFERENCE_CONFIDENT = 0.6;
