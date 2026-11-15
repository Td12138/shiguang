/**
 * 内置换算样例（后端未启动时可完整演示）。
 * 时间全部相对「今天」生成，保证无论哪天演示，倒计时都说得通。
 */
import type {
  AgentRun,
  ExpiryLevel,
  InventoryItem,
  RecognitionResult,
} from './types';

const DAY_MS = 24 * 60 * 60 * 1000;

/** 演示用 run_id，与 MOCK_AGENT_RUN.id 保持一致 */
export const MOCK_RUN_ID = 'run_demo_0001';

/** 相对今天偏移 N 天的 YYYY-MM-DD（演示数据共用） */
export function isoInDays(offset: number): string {
  const date = new Date(Date.now() + offset * DAY_MS);
  const month = `${date.getMonth() + 1}`.padStart(2, '0');
  const day = `${date.getDate()}`.padStart(2, '0');
  return `${date.getFullYear()}-${month}-${day}`;
}

function levelFor(days: number): ExpiryLevel {
  if (days < 0) return 'expired';
  if (days <= 1) return 'urgent';
  if (days <= 3) return 'soon';
  return 'fresh';
}

interface MockSeed {
  id: string;
  name: string;
  qty: number;
  unit: string;
  days: number;
  category: string;
  confidence: number;
}

const MOCK_SEEDS: MockSeed[] = [
  { id: 'inv_demo_01', name: '西兰花', qty: 1, unit: '颗', days: 1, category: '蔬菜', confidence: 0.92 },
  { id: 'inv_demo_02', name: '菠菜', qty: 1, unit: '把', days: 0, category: '蔬菜', confidence: 0.88 },
  { id: 'inv_demo_03', name: '鸡胸肉', qty: 1, unit: '盒', days: 1, category: '肉蛋', confidence: 0.81 },
  { id: 'inv_demo_04', name: '牛奶', qty: 1, unit: '盒', days: 3, category: '乳制品', confidence: 0.64 },
  { id: 'inv_demo_05', name: '香菇', qty: 200, unit: 'g', days: 3, category: '蔬菜', confidence: 0.9 },
  { id: 'inv_demo_06', name: '番茄', qty: 3, unit: '个', days: 5, category: '蔬菜', confidence: 0.95 },
  { id: 'inv_demo_07', name: '鸡蛋', qty: 10, unit: '个', days: 12, category: '肉蛋', confidence: 0.97 },
  { id: 'inv_demo_08', name: '胡萝卜', qty: 2, unit: '根', days: 9, category: '蔬菜', confidence: 0.9 },
  { id: 'inv_demo_09', name: '米', qty: 2, unit: 'kg', days: 120, category: '主食', confidence: 0.86 },
];

export const MOCK_INVENTORY: InventoryItem[] = MOCK_SEEDS.map((seed) => ({
  id: seed.id,
  name: seed.name,
  qty: seed.qty,
  unit: seed.unit,
  expires_at: isoInDays(seed.days),
  days_left: seed.days,
  level: levelFor(seed.days),
  category: seed.category,
  confidence: seed.confidence,
}));

export const MOCK_RECOGNITION: RecognitionResult = {
  image_id: 'img_demo_0001',
  items: [
    {
      name: '西兰花',
      qty: 1,
      unit: '颗',
      confidence: 0.92,
      item_id: 'broccoli',
      shelf_life_days: 5,
      expires_at: isoInDays(5),
      matched: true,
    },
    {
      name: '鸡胸肉',
      qty: 1,
      unit: '盒',
      confidence: 0.81,
      item_id: 'chicken_breast',
      shelf_life_days: 2,
      expires_at: isoInDays(2),
      matched: true,
    },
    {
      name: '酸奶',
      qty: 2,
      unit: '杯',
      confidence: 0.58,
      item_id: 'yogurt',
      shelf_life_days: 7,
      expires_at: isoInDays(7),
      matched: true,
    },
    {
      name: '保鲜盒里的深色块',
      qty: 1,
      unit: '份',
      confidence: 0.31,
      item_id: null,
      shelf_life_days: 3,
      expires_at: isoInDays(3),
      matched: false,
    },
  ],
  warnings: ['第 3、4 项识别置信度较低，请人工确认', '「保鲜盒里的深色块」不在食材库，暂不计入碳账'],
};

export const MOCK_AGENT_RUN: AgentRun = {
  id: MOCK_RUN_ID,
  state: 'ok',
  steps: [
    {
      name: 'understand',
      status: 'ok',
      started_at: new Date(Date.now() - 4200).toISOString(),
      ms: 320,
      summary: '意图：30 分钟内、1 人份、优先消耗临期食材',
    },
    {
      name: 'plan',
      status: 'ok',
      started_at: new Date(Date.now() - 3880).toISOString(),
      ms: 210,
      summary: '调用 list_inventory(sort=expiry) 取前 3 项：菠菜、西兰花、鸡胸肉',
    },
    {
      name: 'retrieve',
      status: 'ok',
      started_at: new Date(Date.now() - 3670).toISOString(),
      ms: 480,
      summary: 'FTS5 召回 12 条，RRF 融合后保留 6 条候选菜谱',
    },
    {
      name: 'compose',
      status: 'ok',
      started_at: new Date(Date.now() - 3190).toISOString(),
      ms: 1260,
      summary: '按临期程度排序并生成理由，引用 recipe:r_012 / recipe:r_031 / tip:7',
    },
    {
      name: 'verify',
      status: 'ok',
      started_at: new Date(Date.now() - 1930).toISOString(),
      ms: 180,
      summary: '规则校验通过：引用 id 均存在、主料均在库存、步骤 ≥3',
    },
  ],
};
