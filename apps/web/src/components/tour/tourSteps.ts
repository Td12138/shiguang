/** §6.16 首次引导的四步：目标元素用 data-tour 标记，缺失时整步跳过 */
export interface TourStep {
  key: string;
  title: string;
  body: string;
  /** 可以命中多个元素（首页要同时圈住两个区块），取并集 */
  selectors: string[];
  /** 该步需要的页面：不同则先导航再定位 */
  path?: string;
}

export const TOUR_STEPS: TourStep[] = [
  {
    key: 'home',
    title: '这里是「今天必须处理」和 AI 建议',
    body: '第一屏先看临期食材的倒计时；下面的 AI 建议会说明为什么这么推荐，角标点开是原文。',
    selectors: ['[data-tour="home-urgent"]', '[data-tour="home-suggest"]'],
    path: '/',
  },
  {
    key: 'capture',
    title: '拍照入库',
    body: '拍冰箱或拍小票都能录入；识别结果一律先人工确认，确认后才写进库存。',
    selectors: ['[data-tour="nav-capture"]'],
  },
  {
    key: 'reconcile',
    title: '库存对账',
    body: '吃了一半、扔了东西，拍一张冰箱照片对账就能校准库存，丢弃会同时记进浪费账。',
    selectors: ['[data-tour="capture-reconcile"]'],
    path: '/capture',
  },
  {
    key: 'plan',
    title: '饮食计划',
    body: '生成 3 天计划，按到期顺序排餐；不满意可以直接对它说「第二天清淡点」。',
    selectors: ['[data-tour="nav-plan"]'],
  },
];
