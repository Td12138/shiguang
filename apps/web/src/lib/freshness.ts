/** §6.14 新鲜度口径：距上次核验超过 3 天视为「未核验」 */
import type { InventoryItem } from '@/lib/api';

export const STALE_DAYS_THRESHOLD = 3;

export function isStale(item: InventoryItem): boolean {
  return typeof item.stale_days === 'number' && item.stale_days > STALE_DAYS_THRESHOLD;
}

export function countStale(items: InventoryItem[]): number {
  return items.filter(isStale).length;
}

/** 食材名 → 未核验天数，给 /plan 的配料角标用 */
export function staleByName(items: InventoryItem[]): Record<string, number> {
  const map: Record<string, number> = {};
  items.forEach((item) => {
    if (isStale(item) && typeof item.stale_days === 'number') {
      map[item.name] = item.stale_days;
    }
  });
  return map;
}
