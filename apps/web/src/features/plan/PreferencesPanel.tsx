import { useState, type FormEvent } from 'react';
import {
  PREFERENCE_CONFIDENT,
  PREFERENCE_KIND_LABELS,
  PREFERENCE_KIND_ORDER,
} from '@/lib/api';
import type { Preference, PreferenceKind } from '@/lib/api';
import { Button } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { Notice } from '@/components/ui/Notice';
import { Skeleton } from '@/components/ui/Skeleton';
import { useToast } from '@/components/ui/Toast';
import { usePreferences } from './usePreferences';
import styles from './PreferencesPanel.module.css';

export interface PreferencesPanelProps {
  /** 计划页整体处于演示模式时，面板不再允许写入 */
  demo?: boolean;
}

const SOURCE_LABEL: Record<string, string> = {
  dialog: '对话推断',
  manual: '手动添加',
};

const KIND_OPTIONS = PREFERENCE_KIND_ORDER.map((kind) => ({
  value: kind,
  label: PREFERENCE_KIND_LABELS[kind],
}));

/** §6.10：按 kind 分组、标注来源、可手动添加与删除 */
export function PreferencesPanel({ demo = false }: PreferencesPanelProps) {
  const prefs = usePreferences();
  const { toast } = useToast();
  const [text, setText] = useState('');
  const [kind, setKind] = useState<PreferenceKind>('avoid');
  const readOnly = demo || prefs.demo;

  const handleAdd = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault();
    const trimmed = text.trim();
    if (!trimmed) {
      toast('先写一条偏好，例如「不吃香菜」', 'info');
      return;
    }
    const ok = await prefs.add(trimmed, kind);
    if (ok) {
      setText('');
      toast('已添加偏好', 'success');
    } else {
      toast('添加失败，原因见下方提示', 'error');
    }
  };

  const handleRemove = async (item: Preference): Promise<void> => {
    const ok = await prefs.remove(item.id);
    toast(ok ? `已删除：${item.text}` : `删除失败：${item.text}`, ok ? 'success' : 'error');
  };

  return (
    <div className={styles.wrap}>
      {readOnly ? (
        <Notice tone="warn" title="演示模式">
          偏好列表来自内置样例，没有连后端；新增与删除要等接口可用后才会生效。
        </Notice>
      ) : null}

      {prefs.error ? (
        <Notice
          tone="error"
          title="偏好操作没有成功"
          action={
            <Button variant="secondary" size="sm" onClick={() => void prefs.reload()}>
              重新读取
            </Button>
          }
        >
          {prefs.error}
        </Notice>
      ) : null}

      {prefs.loading ? (
        <div className={styles.loading}>
          <Skeleton lines={4} height="16px" />
        </div>
      ) : prefs.items.length === 0 ? (
        <EmptyState
          tone="inline"
          title="还没有记住任何偏好"
          description="在改计划时直接说「不要鸡蛋」「清淡点」，我会记住并跨会话生效；也可以下面手动添加。"
        />
      ) : (
        <div className={styles.groups}>
          {PREFERENCE_KIND_ORDER.map((groupKind) => {
            const rows = prefs.items.filter((item) => item.kind === groupKind);
            if (rows.length === 0) return null;
            return (
              <section key={groupKind} className={styles.group}>
                <h3 className={styles.groupTitle}>
                  {PREFERENCE_KIND_LABELS[groupKind]}
                  <span className={styles.count}>{rows.length}</span>
                </h3>
                <ul className={styles.list}>
                  {rows.map((item) => (
                    <li key={item.id} className={styles.item} data-pending={item.confidence < PREFERENCE_CONFIDENT || undefined}>
                      <span className={styles.text}>{item.text}</span>
                      <span className={styles.tag}>{SOURCE_LABEL[item.source] ?? item.source}</span>
                      {item.confidence < PREFERENCE_CONFIDENT ? (
                        <span className={styles.pending}>待确认</span>
                      ) : (
                        <span className={styles.confidence}>{Math.round(item.confidence * 100)}%</span>
                      )}
                      <button
                        type="button"
                        className={styles.remove}
                        onClick={() => void handleRemove(item)}
                        disabled={readOnly || prefs.removingId === item.id}
                        aria-label={`删除偏好：${item.text}`}
                      >
                        {prefs.removingId === item.id ? '…' : '删除'}
                      </button>
                    </li>
                  ))}
                </ul>
              </section>
            );
          })}
        </div>
      )}

      <form className={styles.form} onSubmit={(event) => void handleAdd(event)}>
        <input
          className={styles.input}
          value={text}
          onChange={(event) => setText(event.target.value)}
          placeholder="例如：不吃香菜"
          aria-label="新增偏好内容"
          maxLength={40}
          disabled={readOnly || prefs.adding}
        />
        <select
          className={styles.select}
          value={kind}
          onChange={(event) => setKind(event.target.value as PreferenceKind)}
          aria-label="偏好类型"
          disabled={readOnly || prefs.adding}
        >
          {KIND_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <Button type="submit" size="sm" loading={prefs.adding} disabled={readOnly || prefs.adding}>
          添加
        </Button>
      </form>

      <p className={styles.note}>
        偏好会进知识库并参与下次排餐：忌口是硬约束，其余是软约束；置信度低于 60% 的推断只作提示。
      </p>
    </div>
  );
}
