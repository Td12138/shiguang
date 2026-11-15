import { useCallback, useEffect, useState, type CSSProperties } from 'react';
import { createPortal } from 'react-dom';
import { Button } from '@/components/ui/Button';
import type { TourStep } from './tourSteps';
import styles from './TourOverlay.module.css';

interface Rect {
  top: number;
  left: number;
  width: number;
  height: number;
}

export interface TourOverlayProps {
  step: TourStep;
  index: number;
  total: number;
  onNext: () => void;
  onPrev: () => void;
  onSkip: () => void;
  /** 目标元素不存在（或已隐藏）时跳过该步 */
  onMissing: () => void;
}

const RETRY_MS = 80;
const MAX_RETRIES = 8;
const HIGHLIGHT_PADDING = 8;
const BUBBLE_WIDTH = 340;
const GAP = 16;
const MOBILE_BREAKPOINT = 768;

function visibleRect(el: Element): Rect | null {
  const rect = el.getBoundingClientRect();
  if (rect.width === 0 && rect.height === 0) return null;
  return { top: rect.top, left: rect.left, width: rect.width, height: rect.height };
}

function union(rects: Rect[]): Rect | null {
  if (rects.length === 0) return null;
  const top = Math.min(...rects.map((rect) => rect.top));
  const left = Math.min(...rects.map((rect) => rect.left));
  const right = Math.max(...rects.map((rect) => rect.left + rect.width));
  const bottom = Math.max(...rects.map((rect) => rect.top + rect.height));
  return { top, left, width: right - left, height: bottom - top };
}

/** 引导层：遮罩 + 目标高亮 + 气泡，纯 DOM 实现，移动端气泡贴底且不压住目标 */
export function TourOverlay({ step, index, total, onNext, onPrev, onSkip, onMissing }: TourOverlayProps) {
  const [rect, setRect] = useState<Rect | null>(null);
  const [size, setSize] = useState({
    width: window.innerWidth,
    height: window.innerHeight,
  });

  const measure = useCallback((): boolean => {
    setSize({ width: window.innerWidth, height: window.innerHeight });
    const found: Rect[] = [];
    step.selectors.forEach((selector) => {
      // 同一个 data-tour 可能同时标在侧栏与底部 Tab 上：取所有可见命中
      document.querySelectorAll(selector).forEach((el) => {
        const box = visibleRect(el);
        if (box) found.push(box);
      });
    });
    const merged = union(found);
    setRect(merged);
    return merged !== null;
  }, [step]);

  // 目标可能还没渲染：短轮询几次，仍找不到就跳过该步（不卡死）
  useEffect(() => {
    setRect(null);
    let tries = 0;
    let timer: number | null = null;
    const attempt = (): void => {
      if (measure()) return;
      tries += 1;
      if (tries >= MAX_RETRIES) {
        onMissing();
        return;
      }
      timer = window.setTimeout(attempt, RETRY_MS);
    };
    const raf = window.requestAnimationFrame(attempt);
    return () => {
      window.cancelAnimationFrame(raf);
      if (timer !== null) window.clearTimeout(timer);
    };
  }, [measure, onMissing]);

  // 窗口尺寸与滚动时重算
  useEffect(() => {
    const handler = (): void => {
      measure();
    };
    window.addEventListener('resize', handler);
    window.addEventListener('scroll', handler, true);
    return () => {
      window.removeEventListener('resize', handler);
      window.removeEventListener('scroll', handler, true);
    };
  }, [measure]);

  // 键盘：← → 切换，Esc 跳过
  useEffect(() => {
    const onKey = (event: KeyboardEvent): void => {
      if (event.key === 'ArrowRight') {
        event.preventDefault();
        onNext();
      } else if (event.key === 'ArrowLeft') {
        event.preventDefault();
        onPrev();
      } else if (event.key === 'Escape') {
        event.preventDefault();
        onSkip();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onNext, onPrev, onSkip]);

  if (!rect) return null;

  const viewportWidth = size.width;
  const viewportHeight = size.height;
  const mobile = viewportWidth < MOBILE_BREAKPOINT;
  const width = mobile ? viewportWidth - 24 : Math.min(BUBBLE_WIDTH, viewportWidth - 32);
  const highlight = {
    top: rect.top - HIGHLIGHT_PADDING,
    left: rect.left - HIGHLIGHT_PADDING,
    width: rect.width + HIGHLIGHT_PADDING * 2,
    height: rect.height + HIGHLIGHT_PADDING * 2,
  };
  const placeAbove = highlight.top + highlight.height / 2 > viewportHeight * 0.55;
  const left = mobile ? 12 : Math.min(Math.max(highlight.left, 16), viewportWidth - width - 16);
  const bubbleStyle: CSSProperties = placeAbove
    ? { left, width, bottom: viewportHeight - highlight.top + GAP }
    : { left, width, top: highlight.top + highlight.height + GAP };

  return createPortal(
    <div className={styles.root}>
      <div className={styles.blocker} aria-hidden="true" />
      <div
        className={styles.highlight}
        style={highlight}
        aria-hidden="true"
        data-tour-target={step.key}
      />
      <div
        className={styles.bubble}
        style={bubbleStyle}
        role="dialog"
        aria-modal="true"
        aria-labelledby="tour-title"
      >
        <p className={styles.step}>
          第 {index + 1} / {total} 步
        </p>
        <h2 id="tour-title" className={styles.title}>
          {step.title}
        </h2>
        <p className={styles.body}>{step.body}</p>
        <div className={styles.actions}>
          <Button variant="ghost" size="sm" onClick={onSkip}>
            跳过
          </Button>
          <div className={styles.nav}>
            <Button variant="secondary" size="sm" onClick={onPrev} disabled={index === 0}>
              上一步
            </Button>
            <Button size="sm" onClick={onNext} autoFocus>
              {index + 1 === total ? '开始使用' : '下一步'}
            </Button>
          </div>
        </div>
        <p className={styles.hint}>键盘 ← → 切换 · Esc 跳过</p>
      </div>
    </div>,
    document.body,
  );
}
