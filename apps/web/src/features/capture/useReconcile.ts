import { useCallback, useMemo, useState } from 'react';
import { applyReconcile, describeApiError, loadReconcile } from '@/lib/api';
import type { DiscardReason, MissingAction, ReconcileApplied, ReconcileResult } from '@/lib/api';
import {
  DEFAULT_REASON,
  buildApplyPayload,
  payloadSize,
  reducedQtyErrors,
  summarize,
  type MissingChoice,
} from './reconcileModel';
import { useManualRows } from './useManualRows';
import { newRequestId } from '@/lib/id';
import { uploadSizeError } from '@/lib/upload';
import type { ReconcileState, ReconcileStage } from './reconcileTypes';

export type { MissingChoice, ReconcileSummary } from './reconcileModel';
export type { ReconcileStage, ReconcileState } from './reconcileTypes';

export function useReconcile(): ReconcileState {
  const [stage, setStage] = useState<ReconcileStage>('idle');
  const [result, setResult] = useState<ReconcileResult | null>(null);
  const [demo, setDemo] = useState(false);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [applyError, setApplyError] = useState<string | null>(null);
  const [applied, setApplied] = useState<ReconcileApplied | null>(null);
  const [choices, setChoices] = useState<Record<string, MissingChoice>>({});
  const [reducedQty, setReducedQtyState] = useState<Record<string, string>>({});
  const [addedPicked, setAddedPicked] = useState<Record<string, boolean>>({});
  const [requestId, setRequestId] = useState<string | null>(null);
  const manual = useManualRows();

  const resetChoices = useCallback((): void => {
    setChoices({});
    setReducedQtyState({});
    setAddedPicked({});
  }, []);

  const resetAll = useCallback((): void => {
    resetChoices();
    manual.reset();
    setRequestId(null); // 幂等键失效：下一轮对账重新生成
  }, [resetChoices, manual.reset]);

  const upload = useCallback(
    async (file: File): Promise<void> => {
      const sizeError = uploadSizeError(file);
      if (sizeError) {
        setError(sizeError);
        return;
      }
      setStage('uploading');
      setError(null);
      setApplyError(null);
      setApplied(null);
      setChoices({});
      setReducedQtyState({});
      setAddedPicked({});
      manual.reset();
      setPreviewUrl((previous) => {
        if (previous) URL.revokeObjectURL(previous);
        return URL.createObjectURL(file);
      });

      try {
        const response = await loadReconcile(file);
        setResult(response.data);
        setDemo(response.demo);
        // 识别成功即开启一次新的对账会话：apply 的幂等键在这里生成
        setRequestId(newRequestId());
        setStage('review');
      } catch (err) {
        setResult(null);
        setDemo(false);
        setError(describeApiError(err));
        setStage('idle');
      }
    },
    [resetAll],
  );

  const setMissingAction = useCallback((id: string, action: MissingAction): void => {
    setChoices((previous) => ({
      ...previous,
      [id]: { action, reason: previous[id]?.reason ?? DEFAULT_REASON },
    }));
  }, []);

  const setMissingReason = useCallback((id: string, reason: DiscardReason): void => {
    setChoices((previous) => ({
      ...previous,
      [id]: { action: previous[id]?.action ?? 'keep', reason },
    }));
  }, []);

  const setReducedQty = useCallback((id: string, value: string): void => {
    setReducedQtyState((previous) => ({ ...previous, [id]: value }));
  }, []);

  const toggleAdded = useCallback((name: string): void => {
    setAddedPicked((previous) => ({ ...previous, [name]: !previous[name] }));
  }, []);

  const reducedErrors = useMemo(() => reducedQtyErrors(result, reducedQty), [result, reducedQty]);
  const invalid = manual.invalid || Object.keys(reducedErrors).length > 0;

  const summary = useMemo(
    () => summarize(result, choices, reducedQty, addedPicked, manual.items.length),
    [result, choices, reducedQty, addedPicked, manual.items.length],
  );

  const empty = useMemo(() => {
    if (!result) return false;
    return (
      result.missing.length === 0 &&
      result.reduced.length === 0 &&
      result.added.length === 0 &&
      result.suspect.length === 0
    );
  }, [result]);

  const apply = useCallback(async (): Promise<boolean> => {
    if (invalid) {
      setApplyError('有数量不合法：改成大于 0 的数字（可用 0.5）再应用');
      return false;
    }
    const base = buildApplyPayload(result, choices, reducedQty, addedPicked, manual.items);
    if (payloadSize(base) === 0) {
      setApplyError('没有需要应用的改动：默认全部保留，只有你亲手标记的才会被改');
      return false;
    }

    // 重试必须复用同一个 id，否则会真的重复落库
    const id = requestId ?? newRequestId();
    if (!requestId) setRequestId(id);
    const payload = {
      ...base,
      request_id: id,
      ...(result?.image_id ? { image_id: result.image_id } : {}),
      ...(result?.checked_at ? { checked_at: result.checked_at } : {}),
    };

    setStage('applying');
    setApplyError(null);
    try {
      const response = await applyReconcile(payload);
      setApplied(response.applied);
      resetAll();
      setStage('done');
      return true;
    } catch (err) {
      // 失败保留用户当前选择，只提示原因
      setApplyError(describeApiError(err));
      setStage('review');
      return false;
    }
  }, [result, choices, reducedQty, addedPicked, manual.items, invalid, resetAll, requestId]);

  const reset = useCallback((): void => {
    setStage('idle');
    setResult(null);
    setDemo(false);
    setError(null);
    setApplyError(null);
    setApplied(null);
    resetAll();
    setPreviewUrl((previous) => {
      if (previous) URL.revokeObjectURL(previous);
      return null;
    });
  }, [resetAll]);

  return {
    stage,
    result,
    demo,
    previewUrl,
    error,
    applyError,
    applied,
    choices,
    reducedQty,
    reducedErrors,
    addedPicked,
    summary,
    invalid,
    empty,
    manual,
    upload,
    setMissingAction,
    setMissingReason,
    setReducedQty,
    toggleAdded,
    apply,
    resetChoices,
    reset,
  };
}
