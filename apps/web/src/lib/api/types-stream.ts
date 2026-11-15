/** §6.15 流式接口的事件协议（step / delta / result / error / done） */
import type { AgentStep, AgentStepStatus } from './types-ai';

export interface StreamStepEvent {
  type: 'step';
  name: string;
  status: string;
  ms: number;
  summary: string;
}

export interface StreamDeltaEvent {
  type: 'delta';
  text: string;
}

export interface StreamResultEvent<T> {
  type: 'result';
  /** 与非流式接口响应体逐字段一致 */
  payload: T;
}

export interface StreamErrorEvent {
  type: 'error';
  code: string;
  message: string;
}

export interface StreamDoneEvent {
  type: 'done';
}

export type StreamEvent<T> =
  | StreamStepEvent
  | StreamDeltaEvent
  | StreamResultEvent<T>
  | StreamErrorEvent
  | StreamDoneEvent;

/** step 事件 → AgentStep（started_at 由前端补，后端只保证同名同顺序） */
export function stepFromEvent(event: StreamStepEvent): AgentStep {
  return {
    name: event.name,
    status: event.status as AgentStepStatus,
    started_at: new Date().toISOString(),
    ms: event.ms,
    summary: event.summary,
  };
}
