import styles from './Chip.module.css';

export interface ChipProps {
  label: string;
  selected: boolean;
  onToggle: () => void;
  /** 右侧补充信息，如「剩 1 天」 */
  hint?: string;
  /** 是否显示左侧 +/✓ 标记；纯动作 chip 可关掉 */
  showMark?: boolean;
  disabled?: boolean;
}

/** 可多选的食材 chip（aria-pressed 表达选中态） */
export function Chip({
  label,
  selected,
  onToggle,
  hint,
  showMark = true,
  disabled = false,
}: ChipProps) {
  return (
    <button
      type="button"
      className={styles.chip}
      aria-pressed={selected}
      data-selected={selected || undefined}
      disabled={disabled}
      onClick={onToggle}
    >
      {showMark ? (
        <span className={styles.mark} aria-hidden="true">
          {selected ? '✓' : '+'}
        </span>
      ) : null}
      <span className={styles.label}>{label}</span>
      {hint ? <span className={styles.hint}>{hint}</span> : null}
    </button>
  );
}
