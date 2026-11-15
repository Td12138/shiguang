import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { DemoBanner } from '@/components/ui/DemoBanner';
import { Notice } from '@/components/ui/Notice';
import { Skeleton } from '@/components/ui/Skeleton';
import { useToast } from '@/components/ui/Toast';
import { Dropzone } from './Dropzone';
import { RecognizedRow } from './RecognizedRow';
import { SuccessPanel } from './SuccessPanel';
import { useCapture } from './useCapture';
import styles from './CapturePage.module.css';

export default function CapturePage() {
  const capture = useCapture();
  const { toast } = useToast();
  const navigate = useNavigate();
  const busy = capture.stage === 'uploading' || capture.stage === 'submitting';
  const allIncluded = capture.rows.length > 0 && capture.rows.every((row) => row.included);

  const handleSubmit = async (): Promise<void> => {
    const ok = await capture.submit();
    toast(ok ? '已确认入库' : '入库没有完成，看看提示', ok ? 'success' : 'error');
  };

  const toggleAll = (): void => {
    capture.rows.forEach((row) => {
      if (row.included === allIncluded) capture.toggleRow(row.key);
    });
  };

  return (
    <div className="page-stack">
      {capture.demo ? (
        <DemoBanner
          message="识别接口没有响应，下面这份清单是内置样例，不是你这张照片的真实识别结果。"
          onRetry={capture.reset}
        />
      ) : null}

      {capture.error ? (
        <Notice
          tone="error"
          title="上传没有成功"
          action={
            <Button variant="secondary" size="sm" onClick={capture.reset}>
              重新开始
            </Button>
          }
        >
          {capture.error}
        </Notice>
      ) : null}

      {capture.stage !== 'done' ? (
        <Card
          title="① 选择照片"
          subtitle="拍一张冰箱内部的照片即可；识别出的食材一律先校对，确认后才入库"
        >
          <Dropzone
            onFile={(file) => void capture.upload(file)}
            disabled={busy}
            previewUrl={capture.previewUrl}
          />
        </Card>
      ) : null}

      {capture.stage === 'uploading' ? (
        <Card title="正在识别" subtitle="视觉模型看图 + 匹配食材库，通常几秒">
          <div className={styles.loading}>
            <Skeleton lines={3} height="16px" />
            <Skeleton height="72px" radius="var(--radius-md)" />
            <Skeleton height="72px" radius="var(--radius-md)" />
          </div>
        </Card>
      ) : null}

      {capture.stage === 'review' || capture.stage === 'submitting' ? (
        <Card
          title="② 逐条校对"
          subtitle={`识别到 ${capture.rows.length} 条，需要确认 ${capture.needConfirmCount} 条，已选 ${capture.includedCount} 条`}
          actions={
            <Button variant="ghost" size="sm" onClick={toggleAll}>
              {allIncluded ? '全部取消' : '全部纳入'}
            </Button>
          }
        >
          {capture.warnings.length > 0 ? (
            <Notice tone="warn" title={`识别提示（${capture.warnings.length}）`}>
              <ul className={styles.warnings}>
                {capture.warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            </Notice>
          ) : null}

          <ul className={styles.rows}>
            {capture.rows.map((row) => (
              <RecognizedRow
                key={row.key}
                row={row}
                onChange={capture.updateRow}
                onToggle={capture.toggleRow}
                disabled={capture.stage === 'submitting'}
              />
            ))}
          </ul>

          {capture.submitError ? (
            <Notice
              tone="error"
              title="入库失败"
              action={
                <Button variant="secondary" size="sm" onClick={capture.continueAsDemo}>
                  以演示继续
                </Button>
              }
            >
              {capture.submitError}
            </Notice>
          ) : null}

          <div className={styles.footer}>
            <p className={styles.hint}>
              未匹配食材库的条目不计入碳账；数量 × 平均重量决定克数口径。
            </p>
            <Button
              onClick={() => void handleSubmit()}
              loading={capture.stage === 'submitting'}
              disabled={capture.includedCount === 0}
            >
              确认入库 {capture.includedCount} 条
            </Button>
          </div>
        </Card>
      ) : null}

      {capture.stage === 'done' && capture.added !== null ? (
        <SuccessPanel
          added={capture.added}
          demoSubmit={capture.demoSubmit}
          onReset={capture.reset}
          onPlan={() => navigate('/plan')}
        />
      ) : null}
    </div>
  );
}
