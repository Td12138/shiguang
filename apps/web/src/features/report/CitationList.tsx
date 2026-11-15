import type { Citation } from '@/lib/api';
import { CitationChip } from '@/components/ui/CitationChip';
import styles from './CitationList.module.css';

export interface CitationListProps {
  items: Citation[];
}

/** 周报引用清单：角标可点开原文定位，与正文编号一一对应 */
export function CitationList({ items }: CitationListProps) {
  if (items.length === 0) return null;

  return (
    <section className={styles.wrap} aria-label="引用清单">
      <h3 className={styles.title}>引用（{items.length}）</h3>
      <ul className={styles.list}>
        {items.map((citation, index) => (
          <li key={`${citation.source}-${citation.locator}`} className={styles.item}>
            <CitationChip citation={citation} index={index + 1} />
            <code className={styles.source}>{citation.source}</code>
            <span className={styles.locator}>{citation.locator}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
