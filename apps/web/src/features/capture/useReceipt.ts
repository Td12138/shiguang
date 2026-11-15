import { useCallback, useState } from 'react';
import { MOCK_RECEIPT, createInventory, recognizeReceipt } from '@/lib/api';
import {
  countNeedConfirm,
  isOffline,
  messageOf,
  toInventoryItems,
  toRows,
  type ReceiptRow,
} from './receiptRows';

/** 服务端小票识别上限 */
const MAX_UPLOAD_BYTES = 15 * 1024 * 1024;

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
      setError(messageOf(err, '小票识别失败，请稍后重试'));
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
    const items = toInventoryItems(rows);
    if (items.length === 0) {
      setSubmitError('至少保留一条商品再入库');
      return false;
    }

    setStage('submitting');
    setSubmitError(null);
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
      setSubmitError(messageOf(err, '入库失败，请稍后重试'));
      setStage('review');
      return false;
    }
  }, [rows, purchasedAt]);

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
    setPurchasedAt(null);
    setTotalPrice(null);
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
    upload,
    updateRow,
    toggleRow,
    submit,
    continueAsDemo,
    reset,
  };
}
