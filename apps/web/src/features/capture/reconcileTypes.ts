/** 对账 hook 的状态形状（单独放，避免 useReconcile 超过 200 行） */
import type {
  DiscardReason,
  MissingAction,
  ReconcileApplied,
  ReconcileResult,
} from '@/lib/api';
import type { ManualRowsState } from './useManualRows';
import type { MissingChoice, ReconcileSummary } from './reconcileModel';

export type ReconcileStage = 'idle' | 'uploading' | 'review' | 'applying' | 'done';

export interface ReconcileState {
  stage: ReconcileStage;
  result: ReconcileResult | null;
  demo: boolean;
  previewUrl: string | null;
  error: string | null;
  applyError: string | null;
  applied: ReconcileApplied | null;
  choices: Record<string, MissingChoice>;
  reducedQty: Record<string, string>;
  /** 「变少了」的数量行内错误：inventory_id → 文案 */
  reducedErrors: Record<string, string>;
  addedPicked: Record<string, boolean>;
  summary: ReconcileSummary;
  /** 有非法数量/非法手动行时禁止应用 */
  invalid: boolean;
  /** 四个分组都为空：照片里没有可比对的内容 */
  empty: boolean;
  /** 「新增」组里允许手动加，其它组不放 */
  manual: ManualRowsState;
  upload: (file: File) => Promise<void>;
  setMissingAction: (id: string, action: MissingAction) => void;
  setMissingReason: (id: string, reason: DiscardReason) => void;
  setReducedQty: (id: string, value: string) => void;
  toggleAdded: (name: string) => void;
  apply: () => Promise<boolean>;
  /** 把三类动作复位成安全默认值（全部保留） */
  resetChoices: () => void;
  reset: () => void;
}
