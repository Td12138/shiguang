/** §6.11 小票识别的内置样例（网络不通时演示；含 null 价格与未匹配项） */
import type { ReceiptResult } from './types';

const DAY_MS = 24 * 60 * 60 * 1000;

function dayOffset(offset: number): string {
  const date = new Date(Date.now() + offset * DAY_MS);
  const month = `${date.getMonth() + 1}`.padStart(2, '0');
  const day = `${date.getDate()}`.padStart(2, '0');
  return `${date.getFullYear()}-${month}-${day}`;
}

export const MOCK_RECEIPT: ReceiptResult = {
  image_id: 'img_receipt_demo',
  items: [
    {
      name: '西兰花',
      qty: 2,
      unit: '颗',
      price: 6.5,
      confidence: 0.92,
      item_id: 'broccoli',
      shelf_life_days: 5,
      expires_at: dayOffset(5),
      matched: true,
    },
    {
      name: '鸡胸肉',
      qty: 1,
      unit: '盒',
      price: 12.8,
      confidence: 0.85,
      item_id: 'chicken_breast',
      shelf_life_days: 2,
      expires_at: dayOffset(2),
      matched: true,
    },
    {
      name: '酸奶',
      qty: 3,
      unit: '杯',
      price: null,
      confidence: 0.61,
      item_id: 'yogurt',
      shelf_life_days: 7,
      expires_at: dayOffset(7),
      matched: true,
    },
    {
      name: '进口无糖气泡水',
      qty: 1,
      unit: '箱',
      price: 39.9,
      confidence: 0.44,
      item_id: null,
      shelf_life_days: 30,
      expires_at: dayOffset(30),
      matched: false,
    },
  ],
  purchased_at: dayOffset(-1),
  total_price: 59.2,
  warnings: [
    '演示数据：小票识别接口没有响应，这份清单来自内置样例',
    '第 3 项「酸奶」未识别到价格，price 置为 null（不编造）',
    '「进口无糖气泡水」不在食材库，已标记未匹配（不计入碳账）',
  ],
};
