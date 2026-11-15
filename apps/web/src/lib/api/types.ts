/**
 * API 类型 —— 与 docs/03-定稿与契约.md §6 一一对应。
 * 后端返回的字段名保持 snake_case，不做驼峰转换，避免两套命名漂移。
 */

/** 时效分级：>3 fresh，2–3 soon，0–1 urgent，<0 expired（契约 §6.3） */
export type ExpiryLevel = 'fresh' | 'soon' | 'urgent' | 'expired';

/** 统一错误体 `{code,message,detail?}`（契约 §6） */
export interface ApiErrorBody {
  code: string;
  message: string;
  detail?: string;
}

/* ---------------------------------------------------------------- §6.1 健康 */

export interface HealthResponse {
  ok: boolean;
  provider: string;
  db: string;
}

/* ------------------------------------------------------------ §6.2 拍照识别 */

export interface RecognizedItem {
  name: string;
  qty: number;
  unit: string;
  /** 0–1，< 0.7 时前端标黄并进 warnings */
  confidence: number;
  item_id: string | null;
  shelf_life_days: number;
  /** YYYY-MM-DD */
  expires_at: string;
  /** false = 不在食材库，不计入碳账 */
  matched: boolean;
}

export interface RecognitionResult {
  image_id: string;
  items: RecognizedItem[];
  warnings: string[];
}

/* ---------------------------------------------------------------- §6.3 库存 */

export interface InventoryItem {
  id: string;
  name: string;
  qty: number;
  unit: string;
  expires_at: string;
  /** expires_at - today，可为负 */
  days_left: number;
  level: ExpiryLevel;
  /** 契约未列出，后端若返回则用于「冰箱全景」分组，缺失时归入「其他」 */
  category?: string;
  grams?: number;
  confidence?: number;
  note?: string;
  image_id?: string;
}

export interface CreateInventoryItemInput {
  name: string;
  qty: number;
  unit: string;
  expires_at: string;
  confidence?: number;
}

export interface CreateInventoryRequest {
  image_id?: string;
  items: CreateInventoryItemInput[];
}

export interface CreateInventoryResponse {
  added: number;
  ids: string[];
}

export interface UpdateInventoryInput {
  qty?: number;
  expires_at?: string;
  note?: string;
}

/** consume / discard 的返回体契约只约定语义，此处用宽松结构承接 */
export interface InventoryOperationResult {
  id: string;
  status: string;
  qty?: number;
  grams?: number;
  carbon_kg?: number;
}

export type DiscardReason = 'forgot' | 'spoiled' | 'too_much';

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

export interface StatsSummary {
  waste_rate: number;
  thrown_grams: number;
  saved_grams: number;
  carbon_saved_kg: number;
  money_saved: number;
  equivalents: StatsEquivalents;
  trend: StatsTrendPoint[];
}

/* ---------------------------------------------------------------- §6.6 周报 */

export type WeeklyReportEvent =
  | { type: 'delta'; text: string }
  | { type: 'citations'; items: Citation[] }
  | { type: 'done' };

/* ------------------------------------------------------------ §6.7 Agent trace */

export type AgentStepStatus = 'ok' | 'error' | 'running' | 'pending';

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
