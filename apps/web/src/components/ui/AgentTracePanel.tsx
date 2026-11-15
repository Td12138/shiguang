import { useState } from 'react';
import { loadAgentRun } from '@/lib/api';
import type { AgentRun } from '@/lib/api';
import { AgentTrace } from './AgentTrace';
import { Button } from './Button';
import styles from './AgentTracePanel.module.css';

export interface AgentTracePanelProps {
  /** suggest / plan 返回的 run_id；为空时直接展示样例并标注演示 */
  runId: string | null | undefined;
  /** 展开后若为演示数据，显示这句说明 */
  demoHint?: string;
}

/** Agent trace 折叠面板：懒加载步骤，避免每次进页都多打一次接口 */
export function AgentTracePanel({
  runId,
  demoHint = '演示数据：以下步骤来自内置样例记录',
}: AgentTracePanelProps) {
  const [open, setOpen] = useState(false);
  const [run, setRun] = useState<AgentRun | null>(null);
  const [loading, setLoading] = useState(false);
  const [demo, setDemo] = useState(false);

  const toggle = async (): Promise<void> => {
    if (open) {
      setOpen(false);
      return;
    }
    setOpen(true);
    if (run) return;
    setLoading(true);
    const result = await loadAgentRun(runId ?? null);
    setRun(result.data);
    setDemo(result.demo);
    setLoading(false);
  };

  return (
    <div className={styles.wrap}>
      <Button
        variant="ghost"
        size="sm"
        onClick={toggle}
        aria-expanded={open}
        aria-controls="agent-trace-body"
      >
        {open ? '收起推理过程' : '查看推理过程'}
      </Button>
      {open ? (
        <div id="agent-trace-body" className={styles.body}>
          {demo ? <p className={styles.note}>{demoHint}</p> : null}
          <AgentTrace run={run} loading={loading} />
        </div>
      ) : null}
    </div>
  );
}
