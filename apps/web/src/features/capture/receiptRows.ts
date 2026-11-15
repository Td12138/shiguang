/** 小票校对行的类型与纯函数（放这里让 useReceipt 保持在 200 行内） */
import { ApiError } from '@/lib/api';
import type { CreateInventoryItemInput, ReceiptResult } from '@/lib/api';

/** 与服务端一致：低于该置信度必须人工确认 */
export const LOW_CONFIDENCE = 0.7;
const DEFAULT_QTY = 1;

export interface ReceiptRow {
  key: string;
  name: string;
  /** 以字符串保存，允许输入过程中为空 */
  qty: string;
  unit: string;
  /** 单价：识别不出就是 null，界面显示「—」 */
  price: number | null;
  expiresAt: string;
  confidence: number;
  matched: boolean;
  itemId: string | null;
  included: boolean;
}

export function toRows(result: ReceiptResult): ReceiptRow[] {
  return result.items.map((item, index) => ({
    key: `receipt-${index}-${item.name}`,
    name: item.name,
    qty: `${item.qty}`,
    unit: item.unit,
    price: item.price,
    expiresAt: item.expires_at,
    confidence: item.confidence,
    matched: item.matched,
    itemId: item.item_id,
    included: true,
  }));
}

export function parseQty(raw: string): number {
  const value = Number.parseFloat(raw);
  return Number.isFinite(value) && value > 0 ? value : DEFAULT_QTY;
}

export function toInventoryItems(rows: ReceiptRow[]): CreateInventoryItemInput[] {
  return rows
    .filter((row) => row.included && row.name.trim())
    .map((row) => ({
      name: row.name.trim(),
      qty: parseQty(row.qty),
      unit: row.unit,
      expires_at: row.expiresAt,
      confidence: row.confidence,
      item_id: row.itemId,
    }));
}

export function countNeedConfirm(rows: ReceiptRow[]): number {
  return rows.filter((row) => row.confidence < LOW_CONFIDENCE || !row.matched).length;
}

export function messageOf(err: unknown, fallback: string): string {
  return err instanceof ApiError ? err.message : fallback;
}

/** 只有「后端根本没应答」才回退演示样例；业务错误必须显式提示 */
export function isOffline(err: unknown): boolean {
  if (!(err instanceof ApiError)) return false;
  if (err.code === 'network' || err.code === 'timeout') return true;
  // 代理/网关层失败（如 dev 代理连不上 8720）返回的是非结构化 5xx，
  // 后端自己抛的业务错误一定带 code（vision_unavailable / receipt_empty…），不会被当成离线
  return err.code.startsWith('http_5');
}
