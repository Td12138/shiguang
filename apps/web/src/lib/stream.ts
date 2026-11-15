/** 流式进度的占位与合并：后端只发「已完成的 step」，未到的步骤由前端补灰 */
import type { AgentStep } from '@/lib/api';

/** 契约 §6.9 的固定五步（顺序与 agent_runs 一致） */
export const PLAN_STEP_NAMES = ['understand', 'plan', 'allocate', 'compose', 'verify'] as const;

/** 契约 §6.4 的固定五步 */
export const SUGGEST_STEP_NAMES = ['understand', 'plan', 'retrieve', 'compose', 'verify'] as const;

/** 超过这个时间没有任何 step 事件 → 提示「模型响应较慢」 */
export const SLOW_HINT_MS = 3_000;

function placeholder(name: string, running: boolean): AgentStep {
  return {
    name,
    status: running ? 'running' : 'pending',
    started_at: '',
    ms: 0,
    summary: running ? '进行中…' : '等待中',
  };
}

/**
 * 把「已到达的步骤」铺到完整五步上：
 * 已到的用真实状态，第一个未到的标 running（脉冲），其余 pending（灰）。
 */
export function buildStreamSteps(expected: readonly string[], arrived: AgentStep[]): AgentStep[] {
  const byName = new Map(arrived.map((step) => [step.name, step]));
  let firstMissingSeen = false;

  return expected.map((name) => {
    const hit = byName.get(name);
    if (hit) return hit;
    const running = !firstMissingSeen;
    firstMissingSeen = true;
    return placeholder(name, running);
  });
}
