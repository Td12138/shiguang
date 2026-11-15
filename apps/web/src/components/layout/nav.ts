import type { NavIconName } from './NavIcon';

export interface NavItem {
  path: string;
  /** 导航文案 */
  label: string;
  icon: NavIconName;
  /** 顶部标题栏主标题 */
  title: string;
  /** 顶部标题栏副标题 */
  subtitle: string;
}

const HOME: NavItem = {
  path: '/',
  label: '首页',
  icon: 'home',
  title: '今天先吃这些',
  subtitle: '食光 · 剩食管家 · 绿色生活',
};

/** 导航顺序 = 产品主流程顺序 */
export const NAV_ITEMS: NavItem[] = [
  HOME,
  {
    path: '/capture',
    label: '拍照入库',
    icon: 'camera',
    title: '拍照入库',
    subtitle: '拍一张冰箱照片，识别结果先校对再入库',
  },
  {
    path: '/cook',
    label: '今日吃啥',
    icon: 'pot',
    title: '今天吃什么',
    subtitle: '用临期食材换一顿饭，理由与引用都可核对',
  },
  {
    path: '/stats',
    label: '浪费账本',
    icon: 'ledger',
    title: '浪费账本',
    subtitle: '少扔了多少食物、少排了多少碳',
  },
  {
    path: '/report',
    label: '周报',
    icon: 'report',
    title: '本周周报',
    subtitle: '一周一页，流式生成',
  },
];

/** 按 pathname 找导航项，找不到回落到首页 */
export function findNavItem(pathname: string): NavItem {
  const exact = NAV_ITEMS.find((item) => item.path === pathname);
  if (exact) return exact;
  const nested = NAV_ITEMS.find(
    (item) => item.path !== '/' && pathname.startsWith(`${item.path}/`),
  );
  return nested ?? HOME;
}
