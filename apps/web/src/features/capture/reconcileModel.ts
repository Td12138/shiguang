/** 对账的纯模型层：默认动作、汇总口径与 apply 负载（让 hook 保持精简） */
import { parsePositiveQty } from '@/lib/qty';
import type {
  CreateInventoryItemInput,
  DiscardReason,
  MissingAction,
  ReconcileApplyRequest,
  ReconcileResult,
} from '@/lib/api';

/** 「扔掉了」默认原因；用户可改 */
export const DEFAULT_REASON: DiscardReason = 'spoiled';

export interface MissingChoice {
  action: MissingAction;
  reason: DiscardReason;
}

export interface ReconcileSummary {
  updated: number;
  consumed: number;
  discarded: number;
  added: number;
  total: number;
}

const EMPTY_SUMMARY: ReconcileSummary = { updated: 0, consumed: 0, discarded: 0, added: 0, total: 0 };

/** withFallback=true 时把「用户没改」当成识别值（默认按识别值更新） */
export function reducedQtyOf(
  item: { inventory_id: string; to_qty: number },
  reducedQty: Record<string, string>,
  withFallback = true,
): number | null {
  const raw = reducedQty[item.inventory_id];
  const parsed = raw === undefined ? null : parsePositiveQty(raw);
  if (parsed !== null) return parsed;
  if (withFallback && raw === undefined) return item.to_qty;
  return null;
}

/** 有变化的 reduced 项：用户改过数量且与原值不同 */
export function countUpdated(
  result: ReconcileResult | null,
  reducedQty: Record<string, string>,
): number {
  if (!result) return 0;
  return result.reduced.filter((item) => {
    const value = reducedQtyOf(item, reducedQty);
    return value !== null && value !== item.from_qty;
  }).length;
}

/** 「变少了」的数量校验：必须 >0、不能超过原数量（0 请改用「不见了」） */
export function reducedQtyErrors(
  result: ReconcileResult | null,
  reducedQty: Record<string, string>,
): Record<string, string> {
  const errors: Record<string, string> = {};
  if (!result) return errors;
  result.reduced.forEach((item) => {
    const raw = reducedQty[item.inventory_id];
    if (raw === undefined) return;
    const value = parsePositiveQty(raw);
    if (value === null) {
      errors[item.inventory_id] = '数量要大于 0（可用 0.5）';
      return;
    }
    if (value > item.from_qty) errors[item.inventory_id] = `不能超过原来的 ${item.from_qty}`;
  });
  return errors;
}

export function summarize(
  result: ReconcileResult | null,
  choices: Record<string, MissingChoice>,
  reducedQty: Record<string, string>,
  addedPicked: Record<string, boolean>,
  /** 手动新增的行数（对账只在「新增」组里放开手输） */
  manualCount: number,
): ReconcileSummary {
  if (!result) return EMPTY_SUMMARY;

  const updated = countUpdated(result, reducedQty);
  const consumed = result.missing.filter(
    (item) => choices[item.inventory_id]?.action === 'consumed',
  ).length;
  const discarded = result.missing.filter(
    (item) => choices[item.inventory_id]?.action === 'discarded',
  ).length;
  const added = result.added.filter((item) => addedPicked[item.name]).length + manualCount;

  return { updated, consumed, discarded, added, total: updated + consumed + discarded + added };
}

/** 只提交用户真正改动过的项：default keep / 未改数量 / 未勾选的一律不传 */
export function buildApplyPayload(
  result: ReconcileResult | null,
  choices: Record<string, MissingChoice>,
  reducedQty: Record<string, string>,
  addedPicked: Record<string, boolean>,
  manualItems: CreateInventoryItemInput[],
): ReconcileApplyRequest {
  const payload: ReconcileApplyRequest = { missing: [], reduced: [], added: [] };
  if (!result) return payload;

  result.missing.forEach((item) => {
    const choice = choices[item.inventory_id];
    if (!choice || choice.action === 'keep') return;
    payload.missing.push({
      inventory_id: item.inventory_id,
      action: choice.action,
      ...(choice.action === 'discarded' ? { reason: choice.reason } : {}),
    });
  });

  result.reduced.forEach((item) => {
    const value = reducedQtyOf(item, reducedQty);
    if (value === null || value === item.from_qty) return;
    payload.reduced.push({ inventory_id: item.inventory_id, qty: value });
  });

  result.added.forEach((item) => {
    if (!addedPicked[item.name]) return;
    payload.added.push({ name: item.name, qty: item.qty, unit: item.unit });
  });
  manualItems.forEach((item) => {
    payload.added.push({ name: item.name, qty: item.qty, unit: item.unit });
  });

  return payload;
}

export function payloadSize(payload: ReconcileApplyRequest): number {
  return payload.missing.length + payload.reduced.length + payload.added.length;
}
