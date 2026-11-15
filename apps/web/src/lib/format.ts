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
