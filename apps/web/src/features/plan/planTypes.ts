/** 计划页的类型与选项常量（单独放，避免 usePlan 超过 200 行） */
import type {
  AgentStep,
  InventoryItem,
  LearnedPreference,
  MealPlan,
  PlanChange,
} from '@/lib/api';
import type { PlanDiffState } from './PlanDiff';

/** 契约 §6.8 默认 3 天；2/3/5 覆盖「今晚」「这一周」两类场景 */
export const DAY_OPTIONS = [
  { value: '2', label: '2 天' },
  { value: '3', label: '3 天' },
  { value: '5', label: '5 天' },
] as const;

export const MINUTES_OPTIONS = [
  { value: '20', label: '20 分钟' },
  { value: '30', label: '30 分钟' },
  { value: '45', label: '45 分钟' },
] as const;

export type DaysValue = (typeof DAY_OPTIONS)[number]['value'];
export type MinutesValue = (typeof MINUTES_OPTIONS)[number]['value'];

export interface ReviseOutcome {
  ok: boolean;
  changed: PlanChange[];
  learned: LearnedPreference[];
  message?: string;
}

export interface PlanState {
  days: DaysValue;
  minutes: MinutesValue;
  plan: MealPlan | null;
  inventory: InventoryItem[];
  loading: boolean;
  demo: boolean;
  error: string | null;
  /** 流式生成中（与初次读数分开，便于显示时间线） */
  streaming: boolean;
  streamSteps: AgentStep[];
  streamDelta: string;
  streamSlow: boolean;
  cancelGenerate: () => void;
  revising: boolean;
  reviseError: string | null;
  diff: PlanDiffState | null;
  setDays: (value: DaysValue) => void;
  setMinutes: (value: MinutesValue) => void;
  generate: () => void;
  revise: (instruction: string) => Promise<ReviseOutcome>;
  dismissDiff: () => void;
}
