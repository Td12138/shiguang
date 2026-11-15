import type { ReactNode } from 'react';
import { Card } from '@/components/ui/Card';
import styles from './PagePlaceholder.module.css';

export interface PagePlaceholderProps {
  /** 模块状态标签，如「模块接入中」 */
  status: string;
  title: string;
  description: string;
  /** 该页上线后承担的能力 */
  capabilities: string[];
  /** 依赖的接口（契约 §6） */
  endpoints: string[];
  footnote?: string;
  action?: ReactNode;
}

/**
 * 占位页：给出该模块的职责与接口范围，而不是 TODO。
 * 后续 feature 代理替换页面内容时，直接替换 Page 里的这一块即可。
 */
export function PagePlaceholder({
  status,
  title,
  description,
  capabilities,
  endpoints,
  footnote,
  action,
}: PagePlaceholderProps) {
  return (
    <div className={styles.layout}>
      <Card>
        <div className={styles.main}>
          <span className={styles.status}>{status}</span>
          <h2 className={styles.title}>{title}</h2>
          <p className={styles.description}>{description}</p>
          <ul className={styles.capabilities}>
            {capabilities.map((capability) => (
              <li key={capability}>
                <span className={styles.tick} aria-hidden="true">
                  ✓
                </span>
                {capability}
              </li>
            ))}
          </ul>
          {action ? <div className={styles.action}>{action}</div> : null}
          {footnote ? <p className={styles.footnote}>{footnote}</p> : null}
        </div>
      </Card>

      <Card title="对应接口" subtitle="契约 §6 · JSON">
        <ul className={styles.endpoints}>
          {endpoints.map((endpoint) => (
            <li key={endpoint}>
              <code>{endpoint}</code>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
