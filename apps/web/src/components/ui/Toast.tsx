import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import styles from './Toast.module.css';

export type ToastTone = 'success' | 'error' | 'info';

export interface ToastAction {
  label: string;
  onAction: () => void;
}

export interface ToastOptions {
  action?: ToastAction;
  durationMs?: number;
}

interface ToastItem {
  id: number;
  message: string;
  tone: ToastTone;
  action?: ToastAction;
}

export interface ToastApi {
  /**
   * 弹出提示。带 action 的提示（如「撤销」）默认停留更久。
   * 第三个参数可选，旧的 toast(msg, tone) 调用不受影响。
   */
  toast: (message: string, tone?: ToastTone, options?: ToastOptions) => void;
}

const ToastContext = createContext<ToastApi | null>(null);

/** 单条 toast 停留时长 */
const TOAST_DURATION_MS = 3_200;
/** 带操作按钮的提示要留出点按时间 */
const TOAST_ACTION_DURATION_MS = 8_000;
/** 同时最多显示几条 */
const MAX_VISIBLE_TOASTS = 3;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const seq = useRef(0);

  const dismiss = useCallback((id: number) => {
    setItems((previous) => previous.filter((item) => item.id !== id));
  }, []);

  const toast = useCallback(
    (message: string, tone: ToastTone = 'info', options: ToastOptions = {}) => {
      seq.current += 1;
      const id = seq.current;
      const duration =
        options.durationMs ?? (options.action ? TOAST_ACTION_DURATION_MS : TOAST_DURATION_MS);
      const item: ToastItem = {
        id,
        message,
        tone,
        ...(options.action ? { action: options.action } : {}),
      };
      // 最多同时显示 3 条，避免堆起来挡住底部输入框
      setItems((previous) => [...previous, item].slice(-MAX_VISIBLE_TOASTS));
      window.setTimeout(() => dismiss(id), duration);
    },
    [dismiss],
  );

  const value = useMemo<ToastApi>(() => ({ toast }), [toast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className={styles.viewport} role="status" aria-live="polite">
        {items.map((item) => (
          <div key={item.id} className={styles.toast} data-tone={item.tone}>
            <span className={styles.message}>{item.message}</span>
            {item.action ? (
              <button
                type="button"
                className={styles.action}
                onClick={() => {
                  item.action?.onAction();
                  dismiss(item.id);
                }}
              >
                {item.action.label}
              </button>
            ) : null}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastApi {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast 必须在 <ToastProvider> 内使用');
  return ctx;
}
