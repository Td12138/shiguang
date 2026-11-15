/** 菜谱建议与统计的内置样例（后端未启动时演示用） */
import { MOCK_RUN_ID, isoInDays } from './fixtures';
import type { StatsSummary, SuggestResponse } from './types';

export const MOCK_SUGGESTION: SuggestResponse = {
  run_id: MOCK_RUN_ID,
  warnings: ['演示数据：菜谱、理由与引用来自内置样例，不代表真实检索结果'],
  recommendations: [
    {
      recipe_id: 'r_012',
      title: '蒜蓉西兰花',
      minutes: 15,
      reason: '西兰花明天到期，先吃它最划算；锅里只需要再补一头蒜和食用油。',
      missing: [
        { name: '大蒜', optional: false },
        { name: '食用油', optional: true },
      ],
      citations: [
        {
          source: 'recipe:r_012',
          locator: '步骤 1-3',
          text: '西兰花掰小朵，沸水加盐焯 40 秒捞出沥干；蒜切末小火煸香后大火回锅翻匀。',
        },
        {
          source: 'tip:7',
          locator: '第 2 条',
          text: '西兰花冷藏建议用微湿厨房纸包裹，5 天内吃完，焯水后冷冻可延至 1 个月。',
        },
      ],
      score: 0.83,
    },
    {
      recipe_id: 'r_031',
      title: '菠菜鸡蛋汤',
      minutes: 10,
      reason: '菠菜今天到期，鸡蛋还有 12 天，10 分钟就能出锅，适合当晚餐的汤。',
      missing: [],
      citations: [
        {
          source: 'recipe:r_031',
          locator: '步骤 1-2',
          text: '菠菜切段焯水去草酸；水开后淋蛋液成蛋花，加盐与几滴香油即可。',
        },
      ],
      score: 0.79,
    },
    {
      recipe_id: 'r_044',
      title: '香菇鸡胸肉焖饭',
      minutes: 25,
      reason: '鸡胸肉明天到期，香菇和米都现成；一锅出两餐，明天中午不用再点外卖。',
      missing: [{ name: '生抽', optional: true }],
      citations: [
        {
          source: 'recipe:r_044',
          locator: '步骤 2-5',
          text: '鸡胸肉切丁用生抽抓匀；香菇切片与米同煮，水收干后焖 10 分钟再拌开。',
        },
      ],
      score: 0.74,
    },
  ],
};

export const MOCK_STATS: StatsSummary = {
  waste_rate: 0.18,
  thrown_grams: 820,
  saved_grams: 3400,
  carbon_saved_kg: 5.2,
  money_saved: 86,
  equivalents: { car_km: 38, trees_days: 120 },
  trend: [
    { date: isoInDays(-6), thrown: 0, saved: 400 },
    { date: isoInDays(-5), thrown: 120, saved: 320 },
    { date: isoInDays(-4), thrown: 0, saved: 560 },
    { date: isoInDays(-3), thrown: 260, saved: 280 },
    { date: isoInDays(-2), thrown: 0, saved: 610 },
    { date: isoInDays(-1), thrown: 190, saved: 480 },
    { date: isoInDays(0), thrown: 250, saved: 750 },
  ],
};
