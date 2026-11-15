import styles from './Segmented.module.css';

interface SegmentOption<T extends string> {
  value: T;
  label: string;
}

export interface SegmentedProps<T extends string> {
  /** 这一组的无障碍名称，如「计划天数」 */
  ariaLabel: string;
  options: readonly SegmentOption<T>[];
  value: T;
  onChange: (value: T) => void;
  disabled?: boolean;
}

/** 分段选择器：2/3/5 天、时长上限这类少量互斥选项 */
export function Segmented<T extends string>({
  ariaLabel,
  options,
  value,
  onChange,
  disabled = false,
}: SegmentedProps<T>) {
  return (
    <div className={styles.group} role="group" aria-label={ariaLabel} data-disabled={disabled || undefined}>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          className={styles.item}
          aria-pressed={option.value === value}
          data-active={option.value === value || undefined}
          disabled={disabled}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
