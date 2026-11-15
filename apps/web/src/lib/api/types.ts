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
  /** §6.14 距上次核验的天数；> 3 时前端提示「X 天未核验」 */
  stale_days?: number;
  grams?: number;
  confidence?: number;
  note?: string;
  image_id?: string;
}

export interface CreateInventoryItemInput {
  name: string;
  qty: number;
  unit: string;
  /** 缺省时后端按食材库 shelf_life_days 推算（手动录入可不填） */
  expires_at?: string;
  confidence?: number;
  /** 识别阶段匹配到的食材库 id；带上才能进碳账 */
  item_id?: string | null;
  note?: string;
}

export interface CreateInventoryRequest {
  image_id?: string;
  /** §6.11：小票确认入库时用购物日期（YYYY-MM-DD 也接受），缺省按入库时间 */
  added_at?: string;
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

/** consume 返回整条库存 + 本次扣减克数（apps/server/app/domain/inventory.py） */
export interface ConsumeResult extends InventoryItem {
  consumed_grams: number;
}

/** discard 的返回体契约只约定语义，此处用宽松结构承接 */
export interface InventoryOperationResult {
  id: string;
  status: string;
  qty?: number;
  grams?: number;
  carbon_kg?: number;
}

export type DiscardReason = 'forgot' | 'spoiled' | 'too_much';

/* ---------------------------------------------------------- §6.11 小票识别 */

/** 小票商品行：价格识别不出时为 null（不编造，前端显示「—」） */
export interface ReceiptItem extends RecognizedItem {
  price: number | null;
}

export interface ReceiptResult {
  image_id: string;
  items: ReceiptItem[];
  /** 购物日期 YYYY-MM-DD，识别不出为 null */
  purchased_at: string | null;
  /** 小票合计，识别不出为 null */
  total_price: number | null;
  warnings: string[];
}

/* AI 相关类型（菜谱 / 计划 / Agent / 周报）见 types-ai.ts，计划迭代与偏好见 types-plan.ts，备菜见 types-cook.ts */
export * from './types-ai';
export * from './types-plan';
export * from './types-cook';
export * from './types-reconcile';
