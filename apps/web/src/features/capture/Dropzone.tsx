import { useRef, useState, type ChangeEvent, type DragEvent } from 'react';
import { MAX_UPLOAD_LABEL } from '@/lib/upload';
import styles from './Dropzone.module.css';

/** 与服务端 EXT_BY_MIME 对齐 */
const ACCEPT = 'image/jpeg,image/png,image/webp,image/heic,image/bmp';

export interface DropzoneProps {
  onFile: (file: File) => void;
  disabled?: boolean;
  previewUrl: string | null;
  /** 主提示文案，默认是冰箱照片 */
  title?: string;
  hint?: string;
}

/** 拍照/拖拽上传：拖拽区本身就是 label，键盘可触发 */
export function Dropzone({
  onFile,
  disabled = false,
  previewUrl,
  title,
  hint,
}: DropzoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const handleChange = (event: ChangeEvent<HTMLInputElement>): void => {
    const file = event.target.files?.[0];
    if (file) onFile(file);
    event.target.value = '';
  };

  const handleDrop = (event: DragEvent<HTMLLabelElement>): void => {
    event.preventDefault();
    setDragging(false);
    if (disabled) return;
    const file = event.dataTransfer.files?.[0];
    if (file) onFile(file);
  };

  return (
    <div className={styles.wrap}>
      <label
        className={styles.zone}
        data-dragging={dragging || undefined}
        data-disabled={disabled || undefined}
        onDragOver={(event) => {
          event.preventDefault();
          if (!disabled) setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
      >
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT}
          className={styles.input}
          onChange={handleChange}
          disabled={disabled}
          aria-label="选择冰箱照片"
        />
        {previewUrl ? (
          <img className={styles.preview} src={previewUrl} alt="已上传的冰箱照片预览" />
        ) : (
          <span className={styles.icon} aria-hidden="true">
            <svg viewBox="0 0 48 48" width="36" height="36" fill="none">
              <rect x="6" y="12" width="36" height="26" rx="5" stroke="currentColor" strokeWidth="2.4" />
              <circle cx="24" cy="25" r="7" stroke="currentColor" strokeWidth="2.4" />
              <path d="M18 12l2.5-4h7L30 12" stroke="currentColor" strokeWidth="2.4" strokeLinejoin="round" />
            </svg>
          </span>
        )}
        <span className={styles.title}>
          {disabled ? '正在识别…' : (title ?? '拖一张冰箱照片到这里，或点击选择')}
        </span>
        <span className={styles.hint}>
          {hint ?? `支持 JPG / PNG / WEBP，单张 ≤ ${MAX_UPLOAD_LABEL}；识别结果需人工确认后才入库`}
        </span>
      </label>
    </div>
  );
}
