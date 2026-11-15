import { useCallback, useEffect, useState } from 'react';
import {
  ApiError,
  MOCK_PREFERENCES,
  createPreference,
  deletePreference,
  listPreferences,
} from '@/lib/api';
import type { Preference, PreferenceKind } from '@/lib/api';

export interface PreferencesState {
  items: Preference[];
  loading: boolean;
  /** true = 列表来自内置样例（读接口不可用） */
  demo: boolean;
  /** 读失败或写失败的可读信息 */
  error: string | null;
  adding: boolean;
  removingId: string | null;
  reload: () => Promise<void>;
  add: (text: string, kind: PreferenceKind) => Promise<boolean>;
  remove: (id: string) => Promise<boolean>;
}

function messageOf(err: unknown, fallback: string): string {
  return err instanceof ApiError ? err.message : fallback;
}

export function usePreferences(): PreferencesState {
  const [items, setItems] = useState<Preference[]>([]);
  const [loading, setLoading] = useState(true);
  const [demo, setDemo] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [removingId, setRemovingId] = useState<string | null>(null);

  const reload = useCallback(async (): Promise<void> => {
    setLoading(true);
    setError(null);
    try {
      const result = await listPreferences();
      setItems(result.items);
      setDemo(false);
    } catch {
      // 读失败才回样例；写操作永远走真实接口，避免假装成功
      setItems(MOCK_PREFERENCES.items);
      setDemo(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const add = useCallback(async (text: string, kind: PreferenceKind): Promise<boolean> => {
    setAdding(true);
    setError(null);
    try {
      const created = await createPreference({ text, kind });
      setItems((previous) => [...previous, created]);
      return true;
    } catch (err) {
      setError(messageOf(err, '添加偏好失败'));
      return false;
    } finally {
      setAdding(false);
    }
  }, []);

  const remove = useCallback(async (id: string): Promise<boolean> => {
    setRemovingId(id);
    setError(null);
    try {
      await deletePreference(id);
      setItems((previous) => previous.filter((item) => item.id !== id));
      return true;
    } catch (err) {
      setError(messageOf(err, '删除偏好失败'));
      return false;
    } finally {
      setRemovingId(null);
    }
  }, []);

  return { items, loading, demo, error, adding, removingId, reload, add, remove };
}
