/** 拍冰箱流程的校对行模型与纯函数（从 useCapture 抽出来，保持单文件 ≤200 行） */
import type { RecognizedItem } from '@/lib/api';
import { qtyError } from '@/lib/qty';

/** 与服务端一致：低于该置信度必须人工确认（契约 §6.2） */
export const LOW_CONFIDENCE = 0.7;

export interface DraftRow {
  key: string;
  name: string;
  /** 以字符串保存，允许输入过程中为空 */
  qty: string;
  unit: string;
  expiresAt: string;
  confidence: number;
  matched: boolean;
  itemId: string | null;
  /** 取消勾选的条目不提交 */
  included: boolean;
}

export function toDraftRows(items: RecognizedItem[]): DraftRow[] {
  return items.map((item, index) => ({
    key: `${item.name}-${index}`,
    name: item.name,
    qty: `${item.qty}`,
    unit: item.unit,
    expiresAt: item.expires_at,
    confidence: item.confidence,
    matched: item.matched,
    itemId: item.item_id,
    included: true,
  }));
}

/** 需要人工确认的条数：低置信度或未匹配 */
export function countNeedConfirm(rows: DraftRow[]): number {
  return rows.filter((row) => row.confidence < LOW_CONFIDENCE || !row.matched).length;
}

/** 行内数量错误：合法返回 null（0 与负数都算错） */
export function rowQtyError(row: DraftRow): string | null {
  return qtyError(row.qty);
}
