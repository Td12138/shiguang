import { useCallback, useMemo, useState } from 'react';
import type { CreateInventoryItemInput } from '@/lib/api';
import { DEFAULT_UNIT, findFood } from '@/lib/foods';
import {
  createManualDraft,
  manualDraftError,
  manualDraftState,
  manualDraftToItem,
  type ManualDraft,
} from './manualRows';

export interface ManualRowsState {
  rows: ManualDraft[];
  /** key → 行内错误文案（空行不报错） */
  errors: Record<string, string>;
  /** 有非法行时禁止提交 */
  invalid: boolean;
  /** 可提交的条目（已跳过空行与非法行） */
  items: CreateInventoryItemInput[];
  /** 已填写的行数（不含空行） */
  count: number;
  add: () => void;
  update: (key: string, patch: Partial<ManualDraft>) => void;
  remove: (key: string) => void;
  reset: () => void;
}

export function useManualRows(): ManualRowsState {
  const [rows, setRows] = useState<ManualDraft[]>([]);

  const add = useCallback((): void => {
    setRows((previous) => [...previous, createManualDraft()]);
  }, []);

  const update = useCallback((key: string, patch: Partial<ManualDraft>): void => {
    setRows((previous) =>
      previous.map((row) => {
        if (row.key !== key) return row;
        const next: ManualDraft = { ...row, ...patch };
        // 名称命中食材库、单位还是默认值时，自动带上库内常用单位
        if (patch.name !== undefined && row.unit === DEFAULT_UNIT) {
          const food = findFood(patch.name);
          if (food) next.unit = food.unit;
        }
        return next;
      }),
    );
  }, []);

  const remove = useCallback((key: string): void => {
    setRows((previous) => previous.filter((row) => row.key !== key));
  }, []);

  const reset = useCallback((): void => {
    setRows([]);
  }, []);

  const errors = useMemo(() => {
    const map: Record<string, string> = {};
    rows.forEach((row) => {
      const message = manualDraftError(row);
      if (message) map[row.key] = message;
    });
    return map;
  }, [rows]);

  const items = useMemo(
    () =>
      rows
        .map(manualDraftToItem)
        .filter((item): item is CreateInventoryItemInput => item !== null),
    [rows],
  );

  const count = useMemo(
    () => rows.filter((row) => manualDraftState(row) !== 'blank').length,
    [rows],
  );

  return {
    rows,
    errors,
    invalid: Object.keys(errors).length > 0,
    items,
    count,
    add,
    update,
    remove,
    reset,
  };
}
