import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Card } from '@/components/ui/Card';
import { Segmented } from '@/components/ui/Segmented';
import { FridgeCapture } from './FridgeCapture';
import { ReceiptCapture } from './ReceiptCapture';
import { ReconcileCapture } from './ReconcileCapture';
import styles from './CapturePage.module.css';

type CaptureMode = 'fridge' | 'receipt' | 'reconcile';

const MODE_OPTIONS = [
  { value: 'fridge', label: '拍冰箱' },
  { value: 'receipt', label: '拍小票' },
  { value: 'reconcile', label: '对账' },
] as const;

const MODE_NOTE: Record<CaptureMode, string> = {
  fridge: '拍冰箱内部：识别食材与置信度，逐条校对后入库。',
  receipt: '拍小票 / 外卖单 / 购物截图：批量识别名称、数量与单价，可带购物日期入库。',
  reconcile: '拍冰箱对账：比对「不见了 / 变少了 / 新增 / 看不清」，默认全部保留，删除要你亲手确认。',
};

function readMode(raw: string | null): CaptureMode {
  return raw === 'receipt' || raw === 'reconcile' ? raw : 'fridge';
}

/** 拍照入库入口：三种模式共用「先校对再写库」的原则 */
export default function CapturePage() {
  const [params, setParams] = useSearchParams();
  const [mode, setMode] = useState<CaptureMode>(() => readMode(params.get('tab')));

  // 支持 /capture?tab=reconcile 深链（首页提示条就是这条入口）
  useEffect(() => {
    const next = readMode(params.get('tab'));
    setMode((previous) => (previous === next ? previous : next));
  }, [params]);

  const changeMode = (next: CaptureMode): void => {
    setMode(next);
    setParams(next === 'fridge' ? {} : { tab: next }, { replace: true });
  };

  return (
    <div className="page-stack">
      <Card tone="soft">
        <div className={styles.mode}>
          <Segmented
            ariaLabel="录入方式"
            options={MODE_OPTIONS}
            value={mode}
            onChange={changeMode}
            tour={{ reconcile: 'capture-reconcile' }}
          />
          <p className={styles.modeNote}>{MODE_NOTE[mode]}</p>
        </div>
      </Card>

      {mode === 'fridge' ? <FridgeCapture /> : null}
      {mode === 'receipt' ? <ReceiptCapture /> : null}
      {mode === 'reconcile' ? <ReconcileCapture /> : null}
    </div>
  );
}
