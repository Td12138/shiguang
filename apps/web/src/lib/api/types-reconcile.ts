/**
 * §6.13 库存对账（智能食材对比）的类型。
 * 字段对齐 apps/server 的 reconcile 返回体；动作与原因沿用 §6.3 的枚举。
 */
import type { DiscardReason } from './types';

export interface ReconcileMissing {
  inventory_id: string;
  name: string;
  qty: number;
  unit: string;
  days_left: number;
}

export interface ReconcileReduced {
  inventory_id: string;
  name: string;
  from_qty: number;
  to_qty: number;
  unit: string;
}

export interface ReconcileAdded {
  name: string;
  qty: number;
  unit: string;
  confidence: number;
  matched: boolean;
}

export interface ReconcileSuspect {
  /** 可能是 null：识别到看不出来源的新东西时，后端没有可对应的库存 id */
  inventory_id: string | null;
  name: string;
  reason: string;
}

export interface ReconcileResult {
  image_id: string;
  /** ISO8601 带时区 */
  checked_at: string;
  missing: ReconcileMissing[];
  reduced: ReconcileReduced[];
  added: ReconcileAdded[];
  suspect: ReconcileSuspect[];
  warnings: string[];
}

/** 契约 §6.13：默认 keep，删除必须用户确认 */
export type MissingAction = 'keep' | 'consumed' | 'discarded';

export interface ApplyMissing {
  inventory_id: string;
  action: MissingAction;
  reason?: DiscardReason;
}

export interface ApplyReduced {
  inventory_id: string;
  qty: number;
}

export interface ApplyAdded {
  name: string;
  qty: number;
  unit: string;
}

export interface ReconcileApplyRequest {
  /** 幂等键：一次对账会话一个，重试复用（后端 reconcile_applied 台账按它去重） */
  request_id?: string;
  /** 识别阶段的图片 id，便于后端把核验与图片对上 */
  image_id?: string;
  /** 识别时的小票/核验时间 */
  checked_at?: string;
  missing: ApplyMissing[];
  reduced: ApplyReduced[];
  added: ApplyAdded[];
}

export interface ReconcileApplied {
  discarded: number;
  consumed: number;
  updated: number;
  added: number;
}

export interface ReconcileApplyResult {
  /** 后端回的幂等键（与请求一致或服务端生成） */
  request_id?: string;
  checked_at?: string;
  applied: ReconcileApplied;
  /** 因状态变化被跳过的条数（如已被别处扣减） */
  skipped?: number;
  /** 本次盖了 verified_at 的库存行数 */
  verified?: number;
  warnings: string[];
}

/** 丢弃原因的中文标签（§6.3 的三种） */
export const DISCARD_REASON_LABELS: Record<DiscardReason, string> = {
  forgot: '忘了吃',
  spoiled: '坏了',
  too_much: '做多了',
};
