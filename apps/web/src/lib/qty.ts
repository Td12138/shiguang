/**
 * 数量输入口径：后端 `qty: float, gt=0`，前端允许 0.5 步进。
 * 校验与解析集中在这里，各页面的输入框共用同一套规则。
 */

export const QTY_MIN = 0.5;
export const QTY_STEP = 0.5;

/** 解析成正数；空、非数字、0 与负数一律返回 null */
export function parsePositiveQty(raw: string): number | null {
  if (raw.trim() === '') return null;
  const value = Number.parseFloat(raw);
  return Number.isFinite(value) && value > 0 ? value : null;
}

/** 输入框行内错误：合法返回 null */
export function qtyError(raw: string): string | null {
  if (raw.trim() === '') return '请填写数量';
  const value = Number.parseFloat(raw);
  if (!Number.isFinite(value)) return '数量必须是数字';
  if (value <= 0) return '数量必须大于 0（可用 0.5）';
  return null;
}
