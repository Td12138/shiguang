/** §6.12 备菜流水线的类型（apps/server/app/api/cook.py + domain/cook.py） */

export interface CookSequenceStep {
  /** 从 1 开始的步骤序号 */
  order: number;
  /** HH:MM */
  at: string;
  action: string;
  minutes: number;
  /** 可以同时进行的其他步骤 order；空数组表示串行 */
  parallel_with: number[];
  /** 可选：来源菜谱与定位（LLM 输出时带） */
  source?: string;
  locator?: string;
}

export interface CookSequence {
  total_minutes: number;
  steps: CookSequenceStep[];
  tips: string[];
  warnings: string[];
}

export interface CookSequenceRequest {
  recipe_ids: string[];
  /** HH:MM；缺省由后端按当前时间排，前端也会显式传当前时间 */
  start_at?: string;
}
