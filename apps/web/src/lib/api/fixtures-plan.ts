/** §6.8 饮食计划的内置样例（后端 /api/plan/meals 未就绪时的演示数据） */
import { isoInDays } from './fixtures';
import type { MealPlan } from './types';

export const MOCK_PLAN_RUN_ID = 'run_plan_demo_0001';

export const MOCK_PLAN: MealPlan = {
  plan_id: 'plan_demo_0001',
  run_id: MOCK_PLAN_RUN_ID,
  days: [
    {
      date: isoInDays(0),
      meals: [
        {
          slot: '午餐',
          recipe_id: 'r_031',
          title: '菠菜鸡蛋汤',
          minutes: 10,
          uses: [
            { name: '菠菜', qty: 1, unit: '把', inventory_id: 'inv_demo_02' },
            { name: '鸡蛋', qty: 2, unit: '个', inventory_id: 'inv_demo_07' },
          ],
          missing: [],
          citations: [{ source: 'recipe:r_031', locator: '步骤 1-2' }],
          reason: '菠菜今天到期，10 分钟能出锅',
        },
        {
          slot: '晚餐',
          recipe_id: 'r_012',
          title: '蒜蓉西兰花',
          minutes: 15,
          uses: [{ name: '西兰花', qty: 1, unit: '颗', inventory_id: 'inv_demo_01' }],
          missing: [{ name: '大蒜', optional: false }],
          citations: [
            { source: 'recipe:r_012', locator: '步骤 1-3' },
            { source: 'tip:7', locator: '第 2 条' },
          ],
          reason: '西兰花明天到期，先吃它最划算',
        },
      ],
    },
    {
      date: isoInDays(1),
      meals: [
        {
          slot: '午餐',
          recipe_id: 'r_044',
          title: '香菇鸡胸肉焖饭',
          minutes: 25,
          uses: [
            { name: '鸡胸肉', qty: 1, unit: '盒', inventory_id: 'inv_demo_03' },
            { name: '香菇', qty: 200, unit: 'g', inventory_id: 'inv_demo_05' },
          ],
          missing: [{ name: '生抽', optional: true }],
          citations: [{ source: 'recipe:r_044', locator: '步骤 2-5' }],
          reason: '鸡胸肉明天到期，一锅出两餐',
        },
        {
          slot: '晚餐',
          recipe_id: 'r_052',
          title: '番茄炒蛋',
          minutes: 12,
          uses: [
            { name: '番茄', qty: 2, unit: '个', inventory_id: 'inv_demo_06' },
            { name: '鸡蛋', qty: 2, unit: '个', inventory_id: 'inv_demo_07' },
          ],
          missing: [{ name: '小葱', optional: true }],
          citations: [{ source: 'recipe:r_052', locator: '步骤 1-3' }],
          reason: '番茄还有 5 天，先搭配鸡蛋做掉两个',
        },
      ],
    },
    {
      date: isoInDays(2),
      meals: [
        {
          slot: '午餐',
          recipe_id: 'r_061',
          title: '胡萝卜鸡蛋饼',
          minutes: 20,
          uses: [
            { name: '胡萝卜', qty: 1, unit: '根', inventory_id: 'inv_demo_08' },
            { name: '鸡蛋', qty: 2, unit: '个', inventory_id: 'inv_demo_07' },
          ],
          missing: [{ name: '面粉', optional: false }],
          citations: [{ source: 'recipe:r_061', locator: '步骤 1-4' }],
          reason: '胡萝卜能放到周末，用鸡蛋把早餐也解决掉',
        },
        {
          slot: '晚餐',
          recipe_id: 'r_070',
          title: '牛奶炖蛋',
          minutes: 18,
          uses: [
            { name: '牛奶', qty: 1, unit: '盒', inventory_id: 'inv_demo_04' },
            { name: '鸡蛋', qty: 2, unit: '个', inventory_id: 'inv_demo_07' },
          ],
          missing: [],
          citations: [{ source: 'recipe:r_070', locator: '步骤 1-3' }],
          reason: '牛奶还有 3 天到期，做成甜品当宵夜',
        },
      ],
    },
  ],
  shopping: [
    { name: '大蒜', qty: 1, unit: '头', reason: '蒜蓉西兰花需要，库存没有' },
    { name: '面粉', qty: 200, unit: 'g', reason: '胡萝卜鸡蛋饼需要，库存没有' },
    { name: '小葱', qty: 1, unit: '把', reason: '两道菜可选配料，买一把够用一周' },
  ],
  coverage: { used_items: 6, expiring_used: 3, unused_expiring: 1 },
  warnings: ['演示数据：这份计划来自内置样例，不是真实分配结果'],
};
