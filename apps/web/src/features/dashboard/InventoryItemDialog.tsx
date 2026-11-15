import { useCallback, useEffect, useRef, useState } from 'react';
import {
  DISCARD_REASON_LABELS,
  describeApiError,
  discardInventory,
  updateInventory,
} from '@/lib/api';
import type { DiscardReason, InventoryItem } from '@/lib/api';
import { Button } from '@/components/ui/Button';
import { Modal } from '@/components/ui/Modal';
import { Notice } from '@/components/ui/Notice';
import { formatQty } from '@/lib/format';
import { QTY_MIN, QTY_STEP, parsePositiveQty } from '@/lib/qty';
import styles from './InventoryItemDialog.module.css';

export type InventoryDialogMode = 'edit' | 'discard';

/** 丢弃原因：与契约 §6.3 的三种枚举一致 */
const REASON_OPTIONS: DiscardReason[] = ['forgot', 'spoiled', 'too_much'];
const DEFAULT_REASON: DiscardReason = 'spoiled';

export interface InventoryItemDialogProps {
  item: InventoryItem | null;
  mode: InventoryDialogMode;
  onClose: () => void;
  /** 改数量/到期日成功：把后端返回的整条记录交给页面替换 */
  onUpdated: (item: InventoryItem) => void;
  /** 丢弃成功：页面据此移出当前库存 */
  onDiscarded: (item: InventoryItem) => void;
}

/** 首页卡片的最小编辑入口：改数量/到期日、整条丢弃（写浪费账） */
export function InventoryItemDialog({
  item,
  mode,
  onClose,
  onUpdated,
  onDiscarded,
}: InventoryItemDialogProps) {
  const [qty, setQty] = useState('');
  const [expiresAt, setExpiresAt] = useState('');
  const [reason, setReason] = useState<DiscardReason>(DEFAULT_REASON);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  /** 防双击：Button 的 loading 已禁用，这里再兜一层 */
  const busyRef = useRef(false);

  useEffect(() => {
    if (!item) return;
    setQty(`${item.qty}`);
    setExpiresAt(item.expires_at);
    setReason(DEFAULT_REASON);
    setError(null);
    setBusy(false);
    busyRef.current = false;
  }, [item]);

  const close = useCallback((): void => {
    if (!busyRef.current) onClose();
  }, [onClose]);

  const submitEdit = async (): Promise<void> => {
    if (!item || busyRef.current) return;
    const value = parsePositiveQty(qty);
    if (value === null) {
      setError('数量要大于 0（可用 0.5）');
      return;
    }
    if (!expiresAt) {
      setError('请选择到期日');
      return;
    }

    busyRef.current = true;
    setBusy(true);
    setError(null);
    try {
      const updated = await updateInventory(item.id, {
        qty: value,
        ...(expiresAt !== item.expires_at ? { expires_at: expiresAt } : {}),
      });
      onUpdated(updated);
    } catch (err) {
      setError(describeApiError(err));
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  };

  const submitDiscard = async (): Promise<void> => {
    if (!item || busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setError(null);
    try {
      await discardInventory(item.id, reason);
      onDiscarded(item);
    } catch (err) {
      setError(describeApiError(err));
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  };

  if (!item) return null;

  return (
    <Modal
      open
      title={mode === 'edit' ? `修改「${item.name}」` : `丢弃「${item.name}」`}
      onClose={close}
      footer={
        mode === 'edit' ? (
          <>
            <Button variant="secondary" size="sm" onClick={close} disabled={busy}>
              取消
            </Button>
            <Button size="sm" onClick={() => void submitEdit()} loading={busy}>
              保存
            </Button>
          </>
        ) : (
          <>
            <Button variant="secondary" size="sm" onClick={close} disabled={busy}>
              取消
            </Button>
            <Button
              variant="danger"
              size="sm"
              onClick={() => void submitDiscard()}
              loading={busy}
            >
              确认丢弃
            </Button>
          </>
        )
      }
    >
      {mode === 'edit' ? (
        <>
          <div className={styles.form}>
            <label className={styles.field}>
              <span className={styles.label}>数量（{item.unit}）</span>
              <input
                className={styles.input}
                type="number"
                inputMode="decimal"
                min={QTY_MIN}
                step={QTY_STEP}
                value={qty}
                onChange={(event) => setQty(event.target.value)}
                disabled={busy}
                aria-invalid={Boolean(error) || undefined}
              />
            </label>
            <label className={styles.field}>
              <span className={styles.label}>到期日</span>
              <input
                className={styles.input}
                type="date"
                value={expiresAt}
                onChange={(event) => setExpiresAt(event.target.value)}
                disabled={busy}
                aria-invalid={Boolean(error) || undefined}
              />
            </label>
          </div>
          <p className={styles.hint}>
            改数量会按食材库平均重量重算克数与碳账口径；改到期日会重排临期顺序。
          </p>
        </>
      ) : (
        <>
          <p className={styles.hint}>
            这一条还剩 {formatQty(item.qty, item.unit)}，会整条移出库存，并按剩余克数记入浪费账。
          </p>
          <fieldset className={styles.reasons} disabled={busy}>
            <legend className={styles.label}>丢弃原因</legend>
            {REASON_OPTIONS.map((value) => (
              <label
                key={value}
                className={styles.reason}
                data-active={reason === value || undefined}
              >
                <input
                  type="radio"
                  name="discard-reason"
                  value={value}
                  checked={reason === value}
                  onChange={() => setReason(value)}
                  disabled={busy}
                />
                <span>{DISCARD_REASON_LABELS[value]}</span>
              </label>
            ))}
          </fieldset>
        </>
      )}

      {error ? (
        <Notice tone="error" title={mode === 'edit' ? '修改没有成功' : '丢弃没有成功'}>
          {error}
        </Notice>
      ) : null}
    </Modal>
  );
}
