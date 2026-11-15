/** §6.10 用户偏好的内置样例（后端 /api/preferences 未就绪时演示用） */
import type { PreferenceList } from './types-plan';

const DAY_MS = 24 * 60 * 60 * 1000;

function daysAgo(offset: number): string {
  return new Date(Date.now() - offset * DAY_MS).toISOString();
}

export const MOCK_PREFERENCES: PreferenceList = {
  items: [
    {
      id: 'pref_demo_1',
      text: '不吃香菜',
      kind: 'avoid',
      source: 'manual',
      confidence: 1,
      created_at: daysAgo(6),
    },
    {
      id: 'pref_demo_2',
      text: '喜欢清淡少油',
      kind: 'like',
      source: 'dialog',
      confidence: 0.82,
      created_at: daysAgo(3),
    },
    {
      id: 'pref_demo_3',
      text: '每餐控制在 30 分钟内',
      kind: 'time',
      source: 'dialog',
      confidence: 0.76,
      created_at: daysAgo(2),
    },
    {
      id: 'pref_demo_4',
      text: '一个人吃，份量小',
      kind: 'portion',
      source: 'manual',
      confidence: 1,
      created_at: daysAgo(1),
    },
    {
      id: 'pref_demo_5',
      text: '晚上少吃主食',
      kind: 'health',
      source: 'dialog',
      confidence: 0.54,
      created_at: daysAgo(0),
    },
  ],
};
