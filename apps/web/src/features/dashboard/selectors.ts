import type { InventoryItem } from '@/lib/api';

/** 临期区最多展示的卡片数 */
export const EXPIRING_LIMIT = 6;
/** 送给建议接口的食材数（取最临期的几项） */
const SUGGEST_SEED_LIMIT = 3;

/** 类别展示顺序；未登记的类别统一排到「其他」之后 */
const CATEGORY_ORDER = ['蔬菜', '水果', '肉蛋', '乳制品', '主食', '冷冻', '调味', '其他'];
const FALLBACK_CATEGORY = '其他';

export interface CategoryGroup {
  name: string;
  items: InventoryItem[];
}

export function byDaysLeft(a: InventoryItem, b: InventoryItem): number {
  return a.days_left - b.days_left;
}

/** 临期 = soon / urgent / expired，按剩余天数升序 */
export function pickExpiring(items: InventoryItem[], limit = EXPIRING_LIMIT): InventoryItem[] {
  return items
    .filter((item) => item.level !== 'fresh')
    .sort(byDaysLeft)
    .slice(0, limit);
}

/** 建议接口的 use 参数：最临期的几项 id */
export function pickSuggestSeeds(items: InventoryItem[], limit = SUGGEST_SEED_LIMIT): string[] {
  return [...items]
    .sort(byDaysLeft)
    .slice(0, limit)
    .map((item) => item.id);
}

function categoryRank(name: string): number {
  const index = CATEGORY_ORDER.indexOf(name);
  return index === -1 ? CATEGORY_ORDER.length : index;
}

/** 按类别分组；后端未返回 category 时归入「其他」，不丢数据 */
export function groupByCategory(items: InventoryItem[]): CategoryGroup[] {
  const buckets = new Map<string, InventoryItem[]>();

  for (const item of items) {
    const key = item.category?.trim() ? item.category.trim() : FALLBACK_CATEGORY;
    const bucket = buckets.get(key);
    if (bucket) bucket.push(item);
    else buckets.set(key, [item]);
  }

  return [...buckets.entries()]
    .map(([name, groupItems]) => ({ name, items: [...groupItems].sort(byDaysLeft) }))
    .sort((a, b) => categoryRank(a.name) - categoryRank(b.name));
}
