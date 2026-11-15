/** 拍冰箱 hook 的状态形状（单独放，避免 useCapture 超过 200 行） */
import type { ManualRowsState } from './useManualRows';
import type { DraftRow } from './captureRows';

export type CaptureStage = 'idle' | 'uploading' | 'review' | 'submitting' | 'done';

export interface CaptureState {
  stage: CaptureStage;
  rows: DraftRow[];
  warnings: string[];
  imageId: string | null;
  /** true = 识别结果来自内置样例 */
  demo: boolean;
  previewUrl: string | null;
  error: string | null;
  submitError: string | null;
  added: number | null;
  /** true = 后端未连，入库未真实写入，仅按演示继续 */
  demoSubmit: boolean;
  needConfirmCount: number;
  includedCount: number;
  /** 数量不合法的行：key → 文案 */
  rowErrors: Record<string, string>;
  /** 识别行或手动行有问题时禁止提交 */
  invalid: boolean;
  manual: ManualRowsState;
  upload: (file: File) => Promise<void>;
  updateRow: (key: string, patch: Partial<DraftRow>) => void;
  toggleRow: (key: string) => void;
  submit: () => Promise<boolean>;
  continueAsDemo: () => void;
  reset: () => void;
}
