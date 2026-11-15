/** 食材库速查表（69 种，来源 apps/server/app/data/items.json，用于手输补全与单位建议） */

export interface FoodRef {
  name: string;
  /** 库内常用单位，手输时作为建议值 */
  unit: string;
  category: string;
}

/** 手动录入可选单位（契约与食材库并集） */
export const UNIT_OPTIONS = ['个', '颗', '把', '盒', '袋', '瓶', '根', '杯', '块', '包', '碗', '份'] as const;
export type UnitOption = (typeof UNIT_OPTIONS)[number];
export const DEFAULT_UNIT: UnitOption = '个';

/** datalist 的 id：三个入口共用同一个建议源 */
export const FOOD_LIST_ID = 'shiguang-food-suggestions';

export const FOOD_LIST: FoodRef[] = [
  { name: '西兰花', unit: '颗', category: '蔬菜' },
  { name: '菠菜', unit: '把', category: '蔬菜' },
  { name: '生菜', unit: '颗', category: '蔬菜' },
  { name: '小白菜', unit: '把', category: '蔬菜' },
  { name: '油麦菜', unit: '把', category: '蔬菜' },
  { name: '番茄', unit: '个', category: '蔬菜' },
  { name: '黄瓜', unit: '根', category: '蔬菜' },
  { name: '胡萝卜', unit: '根', category: '蔬菜' },
  { name: '土豆', unit: '个', category: '蔬菜' },
  { name: '洋葱', unit: '个', category: '蔬菜' },
  { name: '大白菜', unit: '颗', category: '蔬菜' },
  { name: '青椒', unit: '个', category: '蔬菜' },
  { name: '茄子', unit: '根', category: '蔬菜' },
  { name: '西葫芦', unit: '根', category: '蔬菜' },
  { name: '香菇', unit: '朵', category: '蔬菜' },
  { name: '金针菇', unit: '袋', category: '蔬菜' },
  { name: '四季豆', unit: '把', category: '蔬菜' },
  { name: '苹果', unit: '个', category: '水果' },
  { name: '香蕉', unit: '根', category: '水果' },
  { name: '橙子', unit: '个', category: '水果' },
  { name: '梨', unit: '个', category: '水果' },
  { name: '葡萄', unit: '串', category: '水果' },
  { name: '草莓', unit: '颗', category: '水果' },
  { name: '蓝莓', unit: '盒', category: '水果' },
  { name: '柠檬', unit: '个', category: '水果' },
  { name: '鸡蛋', unit: '个', category: '肉蛋' },
  { name: '鸡胸肉', unit: '块', category: '肉蛋' },
  { name: '猪里脊', unit: '块', category: '肉蛋' },
  { name: '五花肉', unit: '块', category: '肉蛋' },
  { name: '牛腩', unit: '块', category: '肉蛋' },
  { name: '牛肉末', unit: '盒', category: '肉蛋' },
  { name: '鸡翅', unit: '袋', category: '肉蛋' },
  { name: '冷冻虾仁', unit: '袋', category: '肉蛋' },
  { name: '冷冻牛肉卷', unit: '盒', category: '肉蛋' },
  { name: '三文鱼', unit: '块', category: '肉蛋' },
  { name: '牛奶', unit: '盒', category: '乳品' },
  { name: '酸奶', unit: '杯', category: '乳品' },
  { name: '奶酪', unit: '块', category: '乳品' },
  { name: '黄油', unit: '块', category: '乳品' },
  { name: '北豆腐', unit: '块', category: '豆制品' },
  { name: '嫩豆腐', unit: '盒', category: '豆制品' },
  { name: '豆浆', unit: '袋', category: '豆制品' },
  { name: '豆干', unit: '块', category: '豆制品' },
  { name: '腐竹', unit: '袋', category: '豆制品' },
  { name: '米饭', unit: '碗', category: '主食' },
  { name: '馒头', unit: '个', category: '主食' },
  { name: '面条', unit: '份', category: '主食' },
  { name: '全麦面包', unit: '袋', category: '主食' },
  { name: '饺子皮', unit: '袋', category: '主食' },
  { name: '面粉', unit: '袋', category: '主食' },
  { name: '大蒜', unit: '头', category: '调味' },
  { name: '生姜', unit: '块', category: '调味' },
  { name: '小葱', unit: '把', category: '调味' },
  { name: '生抽', unit: '瓶', category: '调味' },
  { name: '蚝油', unit: '瓶', category: '调味' },
  { name: '食用油', unit: '瓶', category: '调味' },
  { name: '剩炒饭', unit: '盒', category: '剩菜' },
  { name: '剩红烧肉', unit: '盒', category: '剩菜' },
  { name: '剩炒青菜', unit: '盒', category: '剩菜' },
  { name: '剩鸡汤', unit: '盒', category: '剩菜' },
  { name: '菠萝', unit: '个', category: '水果' },
  { name: '玉米', unit: '根', category: '主食' },
  { name: '青豆', unit: '袋', category: '蔬菜' },
  { name: '花椰菜', unit: '棵', category: '蔬菜' },
  { name: '果汁', unit: '瓶', category: '饮料' },
  { name: '饼干', unit: '盒', category: '零食' },
  { name: '麦片', unit: '盒', category: '主食' },
  { name: '甜椒', unit: '个', category: '蔬菜' },
  { name: '面包', unit: '袋', category: '主食' },
];

const BY_NAME = new Map(FOOD_LIST.map((food) => [food.name, food]));

/** 精确匹配食材库；库里没有就返回 undefined（前端据此标「库外食材」） */
export function findFood(name: string): FoodRef | undefined {
  return BY_NAME.get(name.trim());
}

export const FOOD_NAMES: string[] = FOOD_LIST.map((food) => food.name);
