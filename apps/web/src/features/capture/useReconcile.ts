import { useCallback, useMemo, useState } from 'react';
import { ApiError, applyReconcile, loadReconcile } from '@/lib/api';
import type {
  DiscardReason,
  MissingAction,
  ReconcileApplied,
  ReconcileResult,
} from '@/lib/api';
import {
  DEFAULT_REASON,
  buildApplyPayload,
  payloadSize,
  summarize,
  type MissingChoice,
  type ReconcileSummary,
} from './reconcileModel';

/** 服务端上传上限 */
const MAX_UPLOAD_BYTES = 15 * 1024 * 1024;

export type ReconcileStage = 'idle' | 'uploading' | 'review' | 'applying' | 'done';

export type { MissingChoice, ReconcileSummary } from './reconcileModel';

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
  addedPicked: Record<string, boolean>;
  summary: ReconcileSummary;
  /** 四个分组都为空：照片里没有可比对的内容 */
  empty: boolean;
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

function messageOf(err: unknown, fallback: string): string {
  return err instanceof ApiError ? err.message : fallback;
}

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

  const resetChoices = useCallback((): void => {
    setChoices({});
    setReducedQtyState({});
    setAddedPicked({});
  }, []);

  const upload = useCallback(
    async (file: File): Promise<void> => {
      if (file.size > MAX_UPLOAD_BYTES) {
        setError('图片超过 15MB，请压缩后再传');
        return;
      }
      setStage('uploading');
      setError(null);
      setApplyError(null);
      setApplied(null);
      resetChoices();
      setPreviewUrl((previous) => {
        if (previous) URL.revokeObjectURL(previous);
        return URL.createObjectURL(file);
      });

      const response = await loadReconcile(file);
      setResult(response.data);
      setDemo(response.demo);
      setStage('review');
    },
    [resetChoices],
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

  const summary = useMemo(
    () => summarize(result, choices, reducedQty, addedPicked),
    [result, choices, reducedQty, addedPicked],
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
    const payload = buildApplyPayload(result, choices, reducedQty, addedPicked);
    if (payloadSize(payload) === 0) {
      setApplyError('没有需要应用的改动：默认全部保留，只有你亲手标记的才会被改');
      return false;
    }

    setStage('applying');
    setApplyError(null);
    try {
      const response = await applyReconcile(payload);
      setApplied(response.applied);
      resetChoices();
      setStage('done');
      return true;
    } catch (err) {
      // 失败保留用户当前选择，只提示原因
      setApplyError(messageOf(err, '应用失败，请稍后重试'));
      setStage('review');
      return false;
    }
  }, [result, choices, reducedQty, addedPicked, resetChoices]);

  const reset = useCallback((): void => {
    setStage('idle');
    setResult(null);
    setDemo(false);
    setError(null);
    setApplyError(null);
    setApplied(null);
    resetChoices();
    setPreviewUrl((previous) => {
      if (previous) URL.revokeObjectURL(previous);
      return null;
    });
  }, [resetChoices]);

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
    addedPicked,
    summary,
    empty,
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
