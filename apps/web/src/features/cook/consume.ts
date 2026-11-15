/** 「做了」的扣减行：grams 缺省 = 整条扣完；给了 grams 就按克数比例扣 */
import type { InventoryItem } from '@/lib/api';

export interface ConsumeLine {
  id: string;
  grams?: number;
}

/** 按数量折算克数：qty × 该条 grams ÷ 原 qty（数量与克数同比例） */
export function gramsForQty(item: InventoryItem, qty: number): number | undefined {
  if (!item.grams || item.grams <= 0 || item.qty <= 0) return undefined;
  return Math.round((qty * item.grams) / item.qty);
}

/** 剩余数量（用于「扣完剩半个」这类提示） */
export function remainingQty(item: InventoryItem, qty: number): number {
  return Math.max(0, Math.round((item.qty - qty) * 100) / 100);
}
