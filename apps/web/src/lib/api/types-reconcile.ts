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
  inventory_id: string;
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
  applied: ReconcileApplied;
  warnings: string[];
}

/** 丢弃原因的中文标签（§6.3 的三种） */
export const DISCARD_REASON_LABELS: Record<DiscardReason, string> = {
  forgot: '忘了吃',
  spoiled: '坏了',
  too_much: '做多了',
};
