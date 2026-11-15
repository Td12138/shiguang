/**
 * AI 域类型：菜谱建议（§6.4）、周报（§6.6）、Agent trace（§6.7）、饮食计划（§6.8）。
 * 与 types.ts 拆开只为每个文件保持在 200 行内。
 */

/* ---------------------------------------------------------------- §6.4 菜谱 */

/** 引用来源：`recipe:<id>` / `tip:<n>`（契约 §8）；text 为可选的原文摘录 */
export interface Citation {
  source: string;
  locator: string;
  text?: string;
}

export interface MissingIngredient {
  name: string;
  optional: boolean;
}

export interface RecipeRecommendation {
  recipe_id: string;
  title: string;
  minutes: number;
  reason: string;
  missing: MissingIngredient[];
  citations: Citation[];
  /** 0–1 排序分 */
  score: number;
  /**
   * 这道菜用掉的库存明细。qty 与对应库存条目同单位，
   * 「做了」按 qty / 库存 qty 的比例折算克数，不能整条扣完。
   */
  uses?: PlanMealUse[];
}

export interface SuggestRequest {
  use: string[];
  max_minutes?: number;
  limit?: number;
}

/** §6.7：suggest 必须建一条 agent_runs 并在返回体带 run_id */
export interface SuggestResponse {
  run_id: string;
  recommendations: RecipeRecommendation[];
  warnings?: string[];
}

/* ---------------------------------------------------------------- §6.5 统计 */

export interface StatsTrendPoint {
  date: string;
  thrown: number;
  saved: number;
}

export interface StatsEquivalents {
  car_km: number;
  trees_days: number;
}

/** 碳当量口径，由后端下发，前端禁止写死 */
export interface StatsFactors {
  car_kg_per_km: number;
  tree_kg_per_day: number;
}

export interface StatsSummary {
  waste_rate: number;
  thrown_grams: number;
  saved_grams: number;
  carbon_saved_kg: number;
  money_saved: number;
  equivalents: StatsEquivalents;
  trend: StatsTrendPoint[];
  /** 后端额外返回：区间标签（30d / 7d / all）、丢弃碳当量与换算口径 */
  range?: string;
  carbon_thrown_kg?: number;
  factors?: StatsFactors;
}

/* ------------------------------------------------------------ §6.8 饮食计划 */

export interface PlanMealUse {
  name: string;
  /** 与库存条目同单位（后端已折算），用于按比例扣减 */
  qty: number;
  unit: string;
  /** 后端补上后前端可直接按 id 扣库存 */
  inventory_id?: string;
}

export interface PlanMeal {
  slot: string;
  recipe_id: string;
  title: string;
  minutes: number;
  uses: PlanMealUse[];
  missing: MissingIngredient[];
  citations: Citation[];
  reason?: string;
}

export interface PlanDay {
  date: string;
  meals: PlanMeal[];
}

export interface ShoppingItem {
  name: string;
  qty: number;
  unit: string;
  reason: string;
}

export interface PlanCoverage {
  used_items: number;
  expiring_used: number;
  unused_expiring: number;
}

export interface MealPlan {
  plan_id: string;
  run_id: string;
  days: PlanDay[];
  shopping: ShoppingItem[];
  coverage: PlanCoverage;
  warnings: string[];
}

export interface PlanRequest {
  days: number;
  servings: number;
  max_minutes: number;
}

/* ---------------------------------------------------------------- §6.6 周报 */

export type WeeklyReportEvent =
  | { type: 'delta'; text: string }
  | { type: 'citations'; items: Citation[] }
  | { type: 'done' };

/* ------------------------------------------------------------ §6.7 Agent trace */

/**
 * 后端实际会写出这些状态（apps/server/app/domain/recipes.py）：
 * ok / degraded / error / empty / skipped / running。
 * 保留 string 兜底，新增状态不会让前端崩。
 */
export type AgentStepStatus =
  | 'ok'
  | 'degraded'
  | 'error'
  | 'empty'
  | 'skipped'
  | 'running'
  | 'pending';

export interface AgentStep {
  name: string;
  status: AgentStepStatus;
  started_at: string;
  ms: number;
  summary: string;
}

export interface AgentRun {
  id: string;
  state: string;
  steps: AgentStep[];
}

/* ------------------------------------------------------- 前端内部：数据来源标记 */

/** demo=true 表示数据来自 mock，页面必须显示「演示数据」提示条 */
export interface Sourced<T> {
  data: T;
  demo: boolean;
}
