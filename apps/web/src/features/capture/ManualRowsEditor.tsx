import { Button } from '@/components/ui/Button';
import { FoodSuggestions } from './FoodSuggestions';
import { ManualItemRow } from './ManualItemRow';
import type { ManualRowsState } from './useManualRows';
import styles from './ManualRowsEditor.module.css';

export interface ManualRowsEditorProps {
  manual: ManualRowsState;
  addLabel?: string;
  hint?: string;
  disabled?: boolean;
}

/** 手动录入区：补全源 + 若干行 + 添加按钮（三个入口共用） */
export function ManualRowsEditor({
  manual,
  addLabel = '再加一样',
  hint,
  disabled = false,
}: ManualRowsEditorProps) {
  return (
    <div className={styles.editor}>
      <FoodSuggestions />
      {manual.rows.length > 0 ? (
        <ul className={styles.list}>
          {manual.rows.map((row) => (
            <ManualItemRow
              key={row.key}
              draft={row}
              error={manual.errors[row.key] ?? null}
              onChange={manual.update}
              onRemove={manual.remove}
              disabled={disabled}
            />
          ))}
        </ul>
      ) : null}
      <div className={styles.footer}>
        <Button variant="secondary" size="sm" onClick={manual.add} disabled={disabled}>
          ＋ {addLabel}
        </Button>
        <span className={styles.hint}>
          {hint ?? '名称可自动补全（69 种食材）；不在库里也能提交，会标注「库外食材，不计碳账」。'}
        </span>
      </div>
    </div>
  );
}
