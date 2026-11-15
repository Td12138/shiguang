/** 拍冰箱（今日吃啥）hook 的状态形状（单独放，避免 useCook 超过 200 行） */
import type {
  AgentStep,
  InventoryItem,
  RecipeRecommendation,
  SuggestResponse,
} from '@/lib/api';
import type { ConsumeLine } from './consume';

export interface ConsumeOutcome {
  ok: boolean;
  consumed: string[];
  message?: string;
}

export interface CookState {
  inventory: InventoryItem[];
  loading: boolean;
  demo: boolean;
  selected: string[];
  suggestion: SuggestResponse | null;
  suggesting: boolean;
  /** 流式步骤（未到的补灰） */
  streamSteps: AgentStep[];
  streamDelta: string;
  streamSlow: boolean;
  cancelSuggest: () => void;
  error: string | null;
  consuming: boolean;
  doneIds: string[];
  toggle: (id: string) => void;
  selectExpiring: () => void;
  clearSelection: () => void;
  suggest: () => Promise<void>;
  consume: (recipe: RecipeRecommendation, chosen: ConsumeLine[]) => Promise<ConsumeOutcome>;
  reset: () => void;
}
