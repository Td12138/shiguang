import styles from './Chip.module.css';

export interface ChipProps {
  label: string;
  selected: boolean;
  onToggle: () => void;
  /** 右侧补充信息，如「剩 1 天」 */
  hint?: string;
  disabled?: boolean;
}

/** 可多选的食材 chip（aria-pressed 表达选中态） */
export function Chip({ label, selected, onToggle, hint, disabled = false }: ChipProps) {
  return (
    <button
      type="button"
      className={styles.chip}
      aria-pressed={selected}
      data-selected={selected || undefined}
      disabled={disabled}
      onClick={onToggle}
    >
      <span className={styles.mark} aria-hidden="true">
        {selected ? '✓' : '+'}
      </span>
      <span className={styles.label}>{label}</span>
      {hint ? <span className={styles.hint}>{hint}</span> : null}
    </button>
  );
}
