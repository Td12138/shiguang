import { useCallback, useEffect, useRef, useState } from 'react';
import { describeApiError, loadAgentRun } from '@/lib/api';
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
  const [error, setError] = useState<string | null>(null);
  /** 请求票据：runId 变化后旧响应直接作废，避免把上一轮步骤写进来 */
  const ticketRef = useRef(0);

  const load = useCallback(async (id: string | null | undefined): Promise<void> => {
    const ticket = ++ticketRef.current;
    setLoading(true);
    setError(null);
    try {
      const result = await loadAgentRun(id ?? null);
      if (ticketRef.current !== ticket) return;
      setRun(result.data);
      setDemo(result.demo);
    } catch (err) {
      if (ticketRef.current !== ticket) return;
      // 4xx（如 run 不存在 / 需要登录）如实展示，不再当样例
      setError(describeApiError(err));
    } finally {
      if (ticketRef.current === ticket) setLoading(false);
    }
  }, []);

  useEffect(() => {
    // runId 变化：作废旧请求、清空上一轮步骤；面板开着就按新 id 重新懒加载
    ticketRef.current += 1;
    setRun(null);
    setDemo(false);
    setError(null);
    setLoading(false);
    if (open) void load(runId);
    // open 变化由 toggle 自己处理，这里只在 runId 变化时重置
  }, [runId]);

  const toggle = async (): Promise<void> => {
    if (open) {
      setOpen(false);
      return;
    }
    setOpen(true);
    if (run || loading) return;
    await load(runId);
  };

  return (
    <div className={styles.wrap}>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => void toggle()}
        aria-expanded={open}
        aria-controls="agent-trace-body"
      >
        {open ? '收起推理过程' : '查看推理过程'}
      </Button>
      {open ? (
        <div id="agent-trace-body" className={styles.body}>
          {demo ? <p className={styles.note}>{demoHint}</p> : null}
          <AgentTrace run={run} loading={loading} error={error} />
        </div>
      ) : null}
    </div>
  );
}
