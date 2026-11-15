/**
 * 类别兜底：后端 `GET /api/inventory` 目前不返回 category（只在 items 表里），
 * 冰箱全景要分组就先用常见食材名做展示级归类；后端补字段后自动以服务端为准。
 */
import type { InventoryItem } from '@/lib/api';

const CATEGORY_BY_NAME: Record<string, string> = {
  西兰花: '蔬菜',
  菠菜: '蔬菜',
  番茄: '蔬菜',
  西红柿: '蔬菜',
  胡萝卜: '蔬菜',
  黄瓜: '蔬菜',
  土豆: '蔬菜',
  洋葱: '蔬菜',
  生菜: '蔬菜',
  白菜: '蔬菜',
  青椒: '蔬菜',
  香菇: '蔬菜',
  蘑菇: '蔬菜',
  玉米: '蔬菜',
  鸡蛋: '肉蛋',
  鸡胸肉: '肉蛋',
  鸡腿: '肉蛋',
  猪肉: '肉蛋',
  牛肉: '肉蛋',
  虾: '肉蛋',
  鱼: '肉蛋',
  牛奶: '乳制品',
  酸奶: '乳制品',
  奶酪: '乳制品',
  米: '主食',
  米饭: '主食',
  面条: '主食',
  面粉: '主食',
  面包: '主食',
  馒头: '主食',
  苹果: '水果',
  香蕉: '水果',
  橙子: '水果',
  葡萄: '水果',
  蓝莓: '水果',
  柠檬: '水果',
};

/** 先看后端字段，再按名称猜，最后归「其他」 */
export function resolveCategory(item: InventoryItem): string {
  const remote = item.category?.trim();
  if (remote) return remote;
  return CATEGORY_BY_NAME[item.name] ?? '其他';
}
