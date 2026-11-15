/** 展示层格式化工具：只做纯函数，便于后续页面复用与测试 */
import type { ExpiryLevel } from '@/lib/api';

const LEVEL_TEXT: Record<ExpiryLevel, string> = {
  fresh: '新鲜',
  soon: '近期到期',
  urgent: '即将到期',
  expired: '已过期',
};

/** 「剩 2 天 / 今天到期 / 已过期 1 天」 */
export function expiryText(days: number): string {
  if (days < 0) return `已过期 ${Math.abs(days)} 天`;
  if (days === 0) return '今天到期';
  return `剩 ${days} 天`;
}

export function levelText(level: ExpiryLevel): string {
  return LEVEL_TEXT[level];
}

/** 「11-20」 */
export function shortDate(iso: string): string {
  const parts = iso.split('-');
  if (parts.length < 3) return iso;
  const [, month, day] = parts;
  return `${month}-${day}`;
}

/** 「2026 年 11 月 15 日 周六」 */
export function todayLabel(date = new Date()): string {
  return date.toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    weekday: 'long',
  });
}

export function formatPercent(value: number, digits = 0): string {
  return `${(value * 100).toFixed(digits)}%`;
}

/** 克 → 「820 g / 3.4 kg」 */
export function formatGrams(grams: number): string {
  if (grams >= 1000) return `${(grams / 1000).toFixed(1)} kg`;
  return `${Math.round(grams)} g`;
}

/** 0.83 → 「83%」 */
export function formatScore(score: number): string {
  return `${Math.round(score * 100)}%`;
}

const WEEKDAYS = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];

/** 「11/16 周一」：饮食计划按天分栏用 */
export function dayLabel(iso: string): string {
  const date = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(date.getTime())) return iso;
  return `${date.getMonth() + 1}/${date.getDate()} ${WEEKDAYS[date.getDay()] ?? ''}`;
}

/** 当前时间 HH:MM：备菜时间轴默认从「现在」开始排 */
export function nowHhMm(date = new Date()): string {
  return `${`${date.getHours()}`.padStart(2, '0')}:${`${date.getMinutes()}`.padStart(2, '0')}`;
}

/** 金额：null / undefined 一律显示「—」，绝不当 0 展示 */
export function formatMoney(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return `¥${value.toFixed(2)}`;
}

/** ISO 时间 → 「2026-11-15 18:20」；解析失败原样返回 */
export function formatDateTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const pad = (value: number): string => `${value}`.padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

/**
 * 数量展示（全站唯一入口）：
 * - 0.5 + 颗 → 「半颗」；1.5 + 个 → 「1 个半」；2 + 把 → 「2 把」
 * - 没有单位时退回纯数字（0.5 → 「0.5」）
 * - 非 0.5 的小数（如 0.3）按原值显示，不做四舍五入到半
 */
export function formatQty(qty: number, unit?: string): string {
  if (!Number.isFinite(qty)) return '—';
  const text = `${Math.round(qty * 100) / 100}`;
  const trimmedUnit = unit?.trim();
  if (!trimmedUnit) return text;

  const whole = Math.floor(qty);
  const isHalf = Math.abs(qty - whole - 0.5) < 1e-9;
  if (isHalf) return whole === 0 ? `半${trimmedUnit}` : `${whole} ${trimmedUnit}半`;
  return `${text} ${trimmedUnit}`;
}
