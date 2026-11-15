import { useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { DemoBanner } from '@/components/ui/DemoBanner';
import { Notice } from '@/components/ui/Notice';
import { Skeleton } from '@/components/ui/Skeleton';
import { useToast } from '@/components/ui/Toast';
import { formatMoney } from '@/lib/format';
import { Dropzone } from './Dropzone';
import { ReceiptTable } from './ReceiptTable';
import { SuccessPanel } from './SuccessPanel';
import { useReceipt } from './useReceipt';
import styles from './ReceiptCapture.module.css';

/** 「拍小票」流程：上传 → 核对（含单价）→ 带入购物日期入库 */
export function ReceiptCapture() {
  const receipt = useReceipt();
  const { toast } = useToast();
  const navigate = useNavigate();
  const busy = receipt.stage === 'uploading' || receipt.stage === 'submitting';
  const allIncluded = receipt.rows.length > 0 && receipt.rows.every((row) => row.included);

  const onFile = useCallback(
    (file: File): void => {
      void receipt.upload(file);
    },
    [receipt.upload],
  );

  const handleSubmit = async (): Promise<void> => {
    const ok = await receipt.submit();
    toast(ok ? '已按小票入库' : '入库没有完成，看看提示', ok ? 'success' : 'error');
  };

  const toggleAll = (): void => {
    receipt.rows.forEach((row) => {
      if (row.included === allIncluded) receipt.toggleRow(row.key);
    });
  };

  return (
    <>
      {receipt.demo ? (
        <DemoBanner
          message="小票识别接口没有响应，下面这份清单是内置样例，不是你这张小票的真实识别结果。"
          onRetry={receipt.reset}
        />
      ) : null}

      {receipt.error ? (
        <Notice
          tone="error"
          title="小票没有识别成功"
          action={
            <Button variant="secondary" size="sm" onClick={receipt.reset}>
              重新上传
            </Button>
          }
        >
          {receipt.error}
        </Notice>
      ) : null}

      {receipt.stage !== 'done' ? (
        <Card title="① 上传小票" subtitle="小票 / 外卖单 / 购物截图都可以；识别结果先核对再入库">
          <Dropzone
            onFile={onFile}
            disabled={busy}
            previewUrl={receipt.previewUrl}
            title="拖一张小票到这里，或点击选择"
            hint="支持 JPG / PNG / WEBP，单张 ≤ 15MB；价格认不出会显示「—」，不会编造"
          />
        </Card>
      ) : null}

      {receipt.stage === 'uploading' ? (
        <Card title="正在识别小票" subtitle="逐行识别商品、单价与日期，通常几秒">
          <div className={styles.loading}>
            <Skeleton lines={2} height="16px" />
            <Skeleton height="88px" radius="var(--radius-md)" />
            <Skeleton height="88px" radius="var(--radius-md)" />
          </div>
        </Card>
      ) : null}

      {receipt.stage === 'review' || receipt.stage === 'submitting' ? (
        <Card
          title="② 核对小票"
          subtitle={`识别到 ${receipt.rows.length} 项 · 需确认 ${receipt.needConfirmCount} 项 · 已选 ${receipt.includedCount} 项`}
          actions={
            <Button variant="ghost" size="sm" onClick={toggleAll}>
              {allIncluded ? '全部取消' : '全部纳入'}
            </Button>
          }
        >
          <ul className={styles.meta}>
            <li>
              <span className={styles.metaKey}>购买日期</span>
              <strong className={styles.metaValue} data-empty={receipt.purchasedAt === null || undefined}>
                {receipt.purchasedAt ?? '小票未识别出日期'}
              </strong>
            </li>
            <li>
              <span className={styles.metaKey}>合计</span>
              <strong className={styles.metaValue} data-empty={receipt.totalPrice === null || undefined}>
                {receipt.totalPrice === null ? '小票未识别出合计' : formatMoney(receipt.totalPrice)}
              </strong>
            </li>
          </ul>

          {receipt.warnings.length > 0 ? (
            <Notice tone="warn" title={`识别提示（${receipt.warnings.length}）`}>
              <ul className={styles.warnings}>
                {receipt.warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            </Notice>
          ) : null}

          <ReceiptTable
            rows={receipt.rows}
            onChange={receipt.updateRow}
            onToggle={receipt.toggleRow}
            disabled={receipt.stage === 'submitting'}
          />

          {receipt.submitError ? (
            <Notice
              tone="error"
              title="入库失败"
              action={
                <Button variant="secondary" size="sm" onClick={receipt.continueAsDemo}>
                  以演示继续
                </Button>
              }
            >
              {receipt.submitError}
            </Notice>
          ) : null}

          <div className={styles.footer}>
            <p className={styles.hint}>
              {receipt.purchasedAt
                ? '入库时会把「购买日期」记为入库时间；单价保留两位小数。'
                : '小票没识别出购买日期，入库时间按现在记录。'}
            </p>
            <Button
              onClick={() => void handleSubmit()}
              loading={receipt.stage === 'submitting'}
              disabled={receipt.includedCount === 0}
            >
              确认入库 {receipt.includedCount} 项
            </Button>
          </div>
        </Card>
      ) : null}

      {receipt.stage === 'done' && receipt.added !== null ? (
        <SuccessPanel
          added={receipt.added}
          demoSubmit={receipt.demoSubmit}
          onReset={receipt.reset}
          onPlan={() => navigate('/plan')}
        />
      ) : null}
    </>
  );
}
