import { useCallback, useMemo, useState } from 'react';
import { ApiError, MOCK_RECOGNITION, createInventory, isTransportError, recognizeImage } from '@/lib/api';
import type { CreateInventoryItemInput, RecognizedItem } from '@/lib/api';
import { parsePositiveQty } from '@/lib/qty';
import { countNeedConfirm, rowQtyError, toDraftRows, type DraftRow } from './captureRows';
import { useManualRows } from './useManualRows';
import type { CaptureStage, CaptureState } from './captureTypes';

/** 服务端拍照识别上限 15MB，前端先挡一次 */
const MAX_UPLOAD_BYTES = 15 * 1024 * 1024;

export type { CaptureStage, CaptureState } from './captureTypes';

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
  const manual = useManualRows();

  const rowErrors = useMemo(() => {
    const map: Record<string, string> = {};
    rows.forEach((row) => {
      const message = rowQtyError(row);
      if (message) map[row.key] = message;
    });
    return map;
  }, [rows]);

  const invalid = Object.keys(rowErrors).length > 0 || manual.invalid;

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

    const applyRecognition = (items: RecognizedItem[], imageKey: string, warningsList: string[], fromDemo: boolean): void => {
      setDemo(fromDemo);
      setImageId(imageKey);
      setWarnings(warningsList);
      setRows(toDraftRows(items));
      setStage('review');
    };

    try {
      const result = await recognizeImage(file);
      if (result.items.length === 0) {
        setError('这张照片里没有识别出食材：换一张更清楚的，或直接手动录入');
        setStage('idle');
        return;
      }
      applyRecognition(result.items, result.image_id, result.warnings, false);
    } catch (err) {
      if (isTransportError(err)) {
        // 后端没应答才回放样例，页面会显示「演示数据」
        applyRecognition(MOCK_RECOGNITION.items, MOCK_RECOGNITION.image_id, MOCK_RECOGNITION.warnings, true);
        return;
      }
      setError(err instanceof ApiError ? err.message : '识别失败，请稍后重试');
      setStage('idle');
    }
  }, []);

  const updateRow = useCallback((key: string, patch: Partial<DraftRow>): void => {
    setRows((previous) => previous.map((row) => (row.key === key ? { ...row, ...patch } : row)));
  }, []);

  const toggleRow = useCallback((key: string): void => {
    setRows((previous) =>
      previous.map((row) => (row.key === key ? { ...row, included: !row.included } : row)),
    );
  }, []);

  const submit = useCallback(async (): Promise<boolean> => {
    if (invalid) {
      setSubmitError('有数量不合法：改成大于 0 的数字（可用 0.5）再提交');
      return false;
    }

    const fromRows: CreateInventoryItemInput[] = rows
      .filter((row) => row.included && row.name.trim())
      .map((row) => ({
        name: row.name.trim(),
        qty: parsePositiveQty(row.qty) ?? 0,
        unit: row.unit,
        expires_at: row.expiresAt,
        confidence: row.confidence,
        item_id: row.itemId,
      }));
    const items = [...fromRows, ...manual.items];

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
  }, [rows, imageId, invalid, manual.items]);

  const continueAsDemo = useCallback((): void => {
    setAdded(rows.filter((row) => row.included).length + manual.items.length);
    setDemoSubmit(true);
    setSubmitError(null);
    setStage('done');
  }, [rows, manual.items]);

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
    manual.reset();
    setPreviewUrl((previous) => {
      if (previous) URL.revokeObjectURL(previous);
      return null;
    });
  }, [manual]);

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
    needConfirmCount: countNeedConfirm(rows),
    includedCount: rows.filter((row) => row.included).length,
    rowErrors,
    invalid,
    manual,
    upload,
    updateRow,
    toggleRow,
    submit,
    continueAsDemo,
    reset,
  };
}
