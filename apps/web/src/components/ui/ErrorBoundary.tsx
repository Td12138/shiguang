import { Component, type ErrorInfo, type ReactNode } from 'react';
import { Button } from './Button';
import styles from './ErrorBoundary.module.css';

interface ErrorBoundaryProps {
  children: ReactNode;
  /** 切换路由时用它重置边界，避免一个页面崩掉后整站卡死 */
  title?: string;
}

interface ErrorBoundaryState {
  error: Error | null;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  override state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  override componentDidCatch(error: Error, info: ErrorInfo): void {
    // 只落前端控制台，不打后端日志（契约 §10.7：日志脱敏）
    console.error('[食光] 渲染异常', error, info.componentStack);
  }

  private readonly reset = (): void => {
    this.setState({ error: null });
  };

  override render(): ReactNode {
    const { error } = this.state;
    if (!error) return this.props.children;

    return (
      <div className={styles.wrap} role="alert">
        <h2 className={styles.title}>{this.props.title ?? '这个区块没能渲染出来'}</h2>
        <p className={styles.text}>
          已拦截异常，其余页面仍可使用。可以重试这一块，或刷新页面重新加载。
        </p>
        <pre className={styles.detail}>{error.message}</pre>
        <div className={styles.actions}>
          <Button variant="secondary" size="sm" onClick={this.reset}>
            重试
          </Button>
          <Button variant="ghost" size="sm" onClick={() => window.location.reload()}>
            刷新页面
          </Button>
        </div>
      </div>
    );
  }
}
