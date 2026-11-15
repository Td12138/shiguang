import { useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { DemoBanner } from '@/components/ui/DemoBanner';
import { EmptyState } from '@/components/ui/EmptyState';
import { Notice } from '@/components/ui/Notice';
import { Skeleton } from '@/components/ui/Skeleton';
import { useToast } from '@/components/ui/Toast';
import { formatDateTime } from '@/lib/format';
import { MAX_UPLOAD_LABEL } from '@/lib/upload';
import { Dropzone } from './Dropzone';
import { ManualRowsEditor } from './ManualRowsEditor';
import { ReconcileMissingGroup } from './ReconcileMissingGroup';
import { ReconcileAddedGroup, ReconcileReducedGroup, ReconcileSuspectGroup } from './ReconcileOtherGroups';
import { ReconcileResultPanel } from './ReconcileResultPanel';
import { useReconcile } from './useReconcile';
import styles from './ReconcileCapture.module.css';

/** 「对账」流程：拍照 → 四类差异逐条确认 → 应用 */
export function ReconcileCapture() {
  const reconcile = useReconcile();
  const { toast } = useToast();
  const navigate = useNavigate();
  const busy = reconcile.stage === 'uploading' || reconcile.stage === 'applying';
  const showReview =
    (reconcile.stage === 'review' || reconcile.stage === 'applying') &&
    reconcile.result !== null &&
    !reconcile.empty;

  const onFile = useCallback(
    (file: File): void => {
      void reconcile.upload(file);
    },
    [reconcile.upload],
  );

  const handleApply = async (): Promise<void> => {
    const ok = await reconcile.apply();
    toast(ok ? '对账已应用' : '对账没有应用，改动还留着', ok ? 'success' : 'error');
  };

  return (
    <>
      {reconcile.demo ? (
        <DemoBanner
          message="对账接口没有响应，下面的差异来自内置样例；应用不会生效，只用于看清流程。"
          onRetry={reconcile.reset}
        />
      ) : null}

      {reconcile.error ? (
        <Notice
          tone="error"
          title="对账没有完成"
          action={
            <Button variant="secondary" size="sm" onClick={reconcile.reset}>
              重新上传
            </Button>
          }
        >
          {reconcile.error}
        </Notice>
      ) : null}

      {reconcile.stage !== 'done' ? (
        <Card title="① 拍一张冰箱照片" subtitle="只比对在库食材；看不清的会单独列出，不会直接判为消失">
          <Dropzone
            onFile={onFile}
            disabled={busy}
            previewUrl={reconcile.previewUrl}
            title="拖一张冰箱内部照片到这里，或点击选择"
            hint={`支持 JPG / PNG / WEBP，单张 ≤ ${MAX_UPLOAD_LABEL}；默认全部保留，任何删除都需要你亲手确认`}
          />
        </Card>
      ) : null}

      {reconcile.stage === 'uploading' ? (
        <Card title="正在核对" subtitle="识别照片里的食材，再和库存逐项比对">
          <div className={styles.loading}>
            <Skeleton lines={2} height="16px" />
            <Skeleton height="96px" radius="var(--radius-md)" />
            <Skeleton height="96px" radius="var(--radius-md)" />
          </div>
        </Card>
      ) : null}

      {showReview && reconcile.result ? (
        <Card
          title="② 逐类核对"
          subtitle={`核验时间 ${formatDateTime(reconcile.result.checked_at)}`}
          actions={
            <Button variant="ghost" size="sm" onClick={reconcile.resetChoices}>
              全部保留
            </Button>
          }
        >
          {reconcile.result.warnings.length > 0 ? (
            <Notice tone="warn" title={`对账提示（${reconcile.result.warnings.length}）`}>
              <ul className={styles.warnings}>
                {reconcile.result.warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            </Notice>
          ) : null}

          <div className={styles.groups}>
            <ReconcileMissingGroup
              items={reconcile.result.missing}
              choices={reconcile.choices}
              onAction={reconcile.setMissingAction}
              onReason={reconcile.setMissingReason}
              disabled={reconcile.stage === 'applying'}
            />
            <ReconcileReducedGroup
              items={reconcile.result.reduced}
              values={reconcile.reducedQty}
              onChange={reconcile.setReducedQty}
              errors={reconcile.reducedErrors}
              disabled={reconcile.stage === 'applying'}
            />
            <ReconcileAddedGroup
              items={reconcile.result.added}
              picked={reconcile.addedPicked}
              onToggle={reconcile.toggleAdded}
              disabled={reconcile.stage === 'applying'}
            >
              <ManualRowsEditor
                manual={reconcile.manual}
                addLabel="手动加一样"
                hint="对账的手动新增只放在这一组；其它三组都是既有库存，不能凭空补。"
                disabled={reconcile.stage === 'applying'}
              />
            </ReconcileAddedGroup>
            <ReconcileSuspectGroup items={reconcile.result.suspect} />
          </div>

          {reconcile.applyError ? (
            <Notice tone="error" title="应用失败，改动已保留">
              {reconcile.applyError}
            </Notice>
          ) : null}

          <div className={styles.footer}>
            <p className={styles.summary}>
              将更新 <strong>{reconcile.summary.updated}</strong> 项 · 丢弃{' '}
              <strong>{reconcile.summary.discarded}</strong> 项
              <span className={styles.summarySub}>
                吃掉 {reconcile.summary.consumed} 项 · 新增 {reconcile.summary.added} 项
                {reconcile.demo ? ' · 演示数据不会写回' : ''}
              </span>
            </p>
            <Button
              onClick={() => void handleApply()}
              loading={reconcile.stage === 'applying'}
              disabled={reconcile.demo || reconcile.summary.total === 0 || reconcile.invalid}
            >
              应用对账（{reconcile.summary.total} 项）
            </Button>
          </div>
        </Card>
      ) : null}

      {reconcile.empty ? (
        <Card>
          <EmptyState
            title="这张照片里没有可比对的内容"
            description="可能没拍到冰箱内部，或照片太暗。这里默认不会删除任何东西，换一张更清楚的照片再试。"
            action={
              <Button variant="secondary" onClick={reconcile.reset}>
                重新上传
              </Button>
            }
          />
        </Card>
      ) : null}

      {reconcile.stage === 'done' && reconcile.applied ? (
        <ReconcileResultPanel
          applied={reconcile.applied}
          onReset={reconcile.reset}
          onHome={() => navigate('/')}
        />
      ) : null}
    </>
  );
}
