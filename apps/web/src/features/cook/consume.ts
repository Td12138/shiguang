/** 「做了」的扣减行：grams 缺省 = 整条扣完；给了 grams 就按克数比例扣 */
import type { InventoryItem, PlanMealUse } from '@/lib/api';

export interface ConsumeLine {
  id: string;
  grams?: number;
}

/** 按数量折算克数：qty × 该条 grams ÷ 原 qty（数量与克数同比例） */
export function gramsForQty(item: InventoryItem, qty: number): number | undefined {
  if (!item.grams || item.grams <= 0 || item.qty <= 0) return undefined;
  return Math.round((qty * item.grams) / item.qty);
}

/**
 * 菜谱用量 → 扣减行：优先 inventory_id，其次按名称对库存；
 * qty 与库存同单位时按比例折克（10 个鸡蛋用 2 个只扣 2 个），对不上则返回 null 交给用户确认。
 */
export function lineForUse(use: PlanMealUse, inventory: InventoryItem[]): ConsumeLine | null {
  if (!Number.isFinite(use.qty) || use.qty <= 0) return null;
  const byId = use.inventory_id
    ? inventory.find((row) => row.id === use.inventory_id)
    : undefined;
  const item = byId ?? inventory.find((row) => row.name === use.name);
  if (!item) return null;
  // 单位不同时数量不可比，宁可弹确认框也不按错的比例扣
  if (use.unit && item.unit && use.unit !== item.unit) return null;
  const qty = Math.min(use.qty, item.qty);
  const grams = gramsForQty(item, qty);
  return grams === undefined ? { id: item.id } : { id: item.id, grams };
}

/** 剩余数量（用于「扣完剩半个」这类提示） */
export function remainingQty(item: InventoryItem, qty: number): number {
  return Math.max(0, Math.round((item.qty - qty) * 100) / 100);
}
