/** 手动录入行的模型与纯函数（三个入口共用） */
import type { CreateInventoryItemInput } from '@/lib/api';
import { DEFAULT_UNIT, findFood } from '@/lib/foods';
import { parsePositiveQty } from '@/lib/qty';

export interface ManualDraft {
  key: string;
  name: string;
  /** 以字符串保存，允许输入过程中为空 */
  qty: string;
  unit: string;
  /** 可选到期日 YYYY-MM-DD */
  expiresAt: string;
}

let sequence = 0;

export function createManualDraft(): ManualDraft {
  sequence += 1;
  return { key: `manual-${sequence}`, name: '', qty: '1', unit: DEFAULT_UNIT, expiresAt: '' };
}

/** blank = 空行（不提交也不报错）；invalid = 填了一半有问题；ok = 可提交 */
export type ManualDraftState = 'blank' | 'invalid' | 'ok';

export function manualDraftState(draft: ManualDraft): ManualDraftState {
  const name = draft.name.trim();
  const qty = draft.qty.trim();
  const blank = name === '' && draft.expiresAt.trim() === '' && (qty === '' || qty === '1');
  if (blank) return 'blank';
  if (name === '' || parsePositiveQty(qty) === null) return 'invalid';
  return 'ok';
}

export function manualDraftError(draft: ManualDraft): string | null {
  if (manualDraftState(draft) !== 'invalid') return null;
  if (draft.name.trim() === '') return '填一下名称';
  return '数量要大于 0（可用 0.5）';
}

/** 名称不在食材库 → 允许提交，但标「库外食材，不计碳账」 */
export function isExternalFood(name: string): boolean {
  const trimmed = name.trim();
  return trimmed.length > 0 && findFood(trimmed) === undefined;
}

/** 空行与非法行都不产出提交项 */
export function manualDraftToItem(draft: ManualDraft): CreateInventoryItemInput | null {
  if (manualDraftState(draft) !== 'ok') return null;
  const qty = parsePositiveQty(draft.qty);
  if (qty === null) return null;
  const expires = draft.expiresAt.trim();
  return {
    name: draft.name.trim(),
    qty,
    unit: draft.unit,
    confidence: 1,
    ...(expires ? { expires_at: expires } : {}),
  };
}
