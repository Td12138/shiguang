import { useState } from 'react';
import type { Citation } from '@/lib/api';
import { Button } from './Button';
import { Modal } from './Modal';
import styles from './CitationChip.module.css';

export interface CitationChipProps {
  citation: Citation;
  /** 角标序号，从 1 开始；缺省则只显示图标 */
  index?: number;
}

/**
 * 引用角标：点击弹出原文。
 * 契约 §8 只约定 source + locator，原文由检索层附带（text）；缺失时如实说明来源。
 */
export function CitationChip({ citation, index }: CitationChipProps) {
  const [open, setOpen] = useState(false);
  const label = index ? `查看引用 ${index}` : '查看引用';

  return (
    <>
      <button
        type="button"
        className={styles.chip}
        onClick={() => setOpen(true)}
        aria-label={`${label}：${citation.source} ${citation.locator}`}
      >
        {index ? <span aria-hidden="true">{index}</span> : <span aria-hidden="true">§</span>}
      </button>
      <Modal
        open={open}
        title={`引用 ${index ?? ''}`.trim()}
        onClose={() => setOpen(false)}
        footer={
          <Button variant="secondary" size="sm" onClick={() => setOpen(false)}>
            知道了
          </Button>
        }
      >
        <dl className={styles.meta}>
          <dt>来源</dt>
          <dd>
            <code>{citation.source}</code>
          </dd>
          <dt>定位</dt>
          <dd>{citation.locator}</dd>
        </dl>
        <div className={styles.quote}>
          {citation.text ? (
            <p>{citation.text}</p>
          ) : (
            <p className={styles.empty}>
              检索服务未返回原文摘录，此引用指向 <code>{citation.source}</code> 的「{citation.locator}」。
            </p>
          )}
        </div>
        <p className={styles.note}>引用用于核对 AI 结论，不做改写。</p>
      </Modal>
    </>
  );
}
