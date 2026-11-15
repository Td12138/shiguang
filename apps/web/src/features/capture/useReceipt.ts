import { useCallback, useMemo, useRef, useState } from 'react';
import { MOCK_RECEIPT, createInventory, describeApiError, recognizeReceipt } from '@/lib/api';
import {
  countNeedConfirm,
  isOffline,
  rowQtyErrors,
  toInventoryItems,
  toRows,
  type ReceiptRow,
} from './receiptRows';
import { useManualRows, type ManualRowsState } from './useManualRows';
import { uploadSizeError } from '@/lib/upload';

export type ReceiptStage = 'idle' | 'uploading' | 'review' | 'submitting' | 'done';

export interface ReceiptState {
  stage: ReceiptStage;
  rows: ReceiptRow[];
  warnings: string[];
  purchasedAt: string | null;
  totalPrice: number | null;
  /** true = 清单来自内置样例（网络不通） */
  demo: boolean;
  previewUrl: string | null;
  error: string | null;
  submitError: string | null;
  added: number | null;
  demoSubmit: boolean;
  needConfirmCount: number;
  includedCount: number;
  /** 数量非法的行：key → 文案 */
  rowErrors: Record<string, string>;
  /** 识别行或手动行有问题时禁止提交 */
  invalid: boolean;
  manual: ManualRowsState;
  upload: (file: File) => Promise<void>;
  updateRow: (key: string, patch: Partial<ReceiptRow>) => void;
  toggleRow: (key: string) => void;
  submit: () => Promise<boolean>;
  continueAsDemo: () => void;
  reset: () => void;
}

/** 「拍小票」独立 hook：字段与流程和 fridge 流程不同，刻意不合并 */
export function useReceipt(): ReceiptState {
  const [stage, setStage] = useState<ReceiptStage>('idle');
  const [rows, setRows] = useState<ReceiptRow[]>([]);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [purchasedAt, setPurchasedAt] = useState<string | null>(null);
  const [totalPrice, setTotalPrice] = useState<number | null>(null);
  const [demo, setDemo] = useState(false);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [added, setAdded] = useState<number | null>(null);
  const [demoSubmit, setDemoSubmit] = useState(false);
  const manual = useManualRows();
  /** 提交进行中的同步锁：防双击重复入库 */
  const submittingRef = useRef(false);

  const rowErrors = useMemo(() => rowQtyErrors(rows), [rows]);
  const invalid = Object.keys(rowErrors).length > 0 || manual.invalid;

  const upload = useCallback(async (file: File): Promise<void> => {
    const sizeError = uploadSizeError(file);
    if (sizeError) {
      setError(sizeError);
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

    try {
      const result = await recognizeReceipt(file);
      if (result.items.length === 0) {
        setError('没有从这张小票里识别出商品，换一张更清晰的图片再试');
        setStage('idle');
        return;
      }
      setDemo(false);
      setWarnings(result.warnings);
      setPurchasedAt(result.purchased_at);
      setTotalPrice(result.total_price);
      setRows(toRows(result));
      setStage('review');
    } catch (err) {
      if (isOffline(err)) {
        // 后端没起时用内置样例演示，页面会显示「演示数据」
        setDemo(true);
        setWarnings(MOCK_RECEIPT.warnings);
        setPurchasedAt(MOCK_RECEIPT.purchased_at);
        setTotalPrice(MOCK_RECEIPT.total_price);
        setRows(toRows(MOCK_RECEIPT));
        setStage('review');
        return;
      }
      setError(describeApiError(err));
      setStage('idle');
    }
  }, []);

  const updateRow = useCallback((key: string, patch: Partial<ReceiptRow>): void => {
    setRows((previous) => previous.map((row) => (row.key === key ? { ...row, ...patch } : row)));
  }, []);

  const toggleRow = useCallback((key: string): void => {
    setRows((previous) =>
      previous.map((row) => (row.key === key ? { ...row, included: !row.included } : row)),
    );
  }, []);

  const submit = useCallback(async (): Promise<boolean> => {
    if (submittingRef.current) return false;
    if (invalid) {
      setSubmitError('有数量不合法：改成大于 0 的数字（可用 0.5）再提交');
      return false;
    }
    const items = [...toInventoryItems(rows), ...manual.items];
    if (items.length === 0) {
      setSubmitError('至少保留一条商品再入库');
      return false;
    }

    setStage('submitting');
    setSubmitError(null);
    submittingRef.current = true;
    try {
      const response = await createInventory({
        // 契约 §6.11：购物日期只在小票识别出来时才带上
        ...(purchasedAt ? { added_at: purchasedAt } : {}),
        items,
      });
      setAdded(response.added);
      setDemoSubmit(false);
      setStage('done');
      return true;
    } catch (err) {
      setSubmitError(describeApiError(err));
      setStage('review');
      return false;
    } finally {
      submittingRef.current = false;
    }
  }, [rows, purchasedAt, invalid, manual.items]);

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
    setPurchasedAt(null);
    setTotalPrice(null);
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
    purchasedAt,
    totalPrice,
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
