import { useCallback, useState } from 'react';
import { ApiError, createInventory, loadRecognition } from '@/lib/api';
import type { CreateInventoryItemInput } from '@/lib/api';

/** 与服务端一致：低于该置信度必须人工确认（契约 §6.2） */
const LOW_CONFIDENCE = 0.7;
/** 服务端拍照识别上限 15MB，前端先挡一次 */
const MAX_UPLOAD_BYTES = 15 * 1024 * 1024;
const DEFAULT_QTY = 1;

export type CaptureStage = 'idle' | 'uploading' | 'review' | 'submitting' | 'done';

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
  upload: (file: File) => Promise<void>;
  updateRow: (key: string, patch: Partial<DraftRow>) => void;
  toggleRow: (key: string) => void;
  submit: () => Promise<boolean>;
  continueAsDemo: () => void;
  reset: () => void;
}

function isLowConfidence(row: DraftRow): boolean {
  return row.confidence < LOW_CONFIDENCE || !row.matched;
}

function parseQty(raw: string): number {
  const value = Number.parseFloat(raw);
  return Number.isFinite(value) && value > 0 ? value : DEFAULT_QTY;
}

function messageOf(err: unknown): string {
  return err instanceof ApiError ? err.message : '入库失败，请稍后重试';
}

export function useCapture(): CaptureState {
  const [stage, setStage] = useState<CaptureStage>('idle');
  const [rows, setRows] = useState<DraftRow[]>([]);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [imageId, setImageId] = useState<string | null>(null);
  const [demo, setDemo] = useState(false);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [added, setAdded] = useState<number | null>(null);
  const [demoSubmit, setDemoSubmit] = useState(false);

  const upload = useCallback(async (file: File): Promise<void> => {
    if (file.size > MAX_UPLOAD_BYTES) {
      setError('图片超过 15MB，请压缩后再传');
      return;
    }
    setError(null);
    setSubmitError(null);
    setAdded(null);
    setDemoSubmit(false);
    setStage('uploading');
    setPreviewUrl((previous) => {
      if (previous) URL.revokeObjectURL(previous);
      return URL.createObjectURL(file);
    });

    const result = await loadRecognition(file);
    setDemo(result.demo);
    setImageId(result.data.image_id);
    setWarnings(result.data.warnings);
    setRows(
      result.data.items.map((item, index) => ({
        key: `${item.name}-${index}`,
        name: item.name,
        qty: `${item.qty}`,
        unit: item.unit,
        expiresAt: item.expires_at,
        confidence: item.confidence,
        matched: item.matched,
        itemId: item.item_id,
        included: true,
      })),
    );
    setStage('review');
  }, []);

  const updateRow = useCallback((key: string, patch: Partial<DraftRow>): void => {
    setRows((previous) =>
      previous.map((row) => (row.key === key ? { ...row, ...patch } : row)),
    );
  }, []);

  const toggleRow = useCallback((key: string): void => {
    setRows((previous) =>
      previous.map((row) => (row.key === key ? { ...row, included: !row.included } : row)),
    );
  }, []);

  const submit = useCallback(async (): Promise<boolean> => {
    const items: CreateInventoryItemInput[] = rows
      .filter((row) => row.included && row.name.trim())
      .map((row) => ({
        name: row.name.trim(),
        qty: parseQty(row.qty),
        unit: row.unit,
        expires_at: row.expiresAt,
        confidence: row.confidence,
        item_id: row.itemId,
      }));

    if (items.length === 0) {
      setSubmitError('至少保留一条食材再入库');
      return false;
    }

    setStage('submitting');
    setSubmitError(null);
    try {
      const response = await createInventory({
        ...(imageId ? { image_id: imageId } : {}),
        items,
      });
      setAdded(response.added);
      setDemoSubmit(false);
      setStage('done');
      return true;
    } catch (err) {
      setSubmitError(messageOf(err));
      setStage('review');
      return false;
    }
  }, [rows, imageId]);

  const continueAsDemo = useCallback((): void => {
    setAdded(rows.filter((row) => row.included).length);
    setDemoSubmit(true);
    setSubmitError(null);
    setStage('done');
  }, [rows]);

  const reset = useCallback((): void => {
    setStage('idle');
    setRows([]);
    setWarnings([]);
    setImageId(null);
    setDemo(false);
    setDemoSubmit(false);
    setError(null);
    setSubmitError(null);
    setAdded(null);
    setPreviewUrl((previous) => {
      if (previous) URL.revokeObjectURL(previous);
      return null;
    });
  }, []);

  return {
    stage,
    rows,
    warnings,
    imageId,
    demo,
    previewUrl,
    error,
    submitError,
    added,
    demoSubmit,
    needConfirmCount: rows.filter(isLowConfidence).length,
    includedCount: rows.filter((row) => row.included).length,
    upload,
    updateRow,
    toggleRow,
    submit,
    continueAsDemo,
    reset,
  };
}
