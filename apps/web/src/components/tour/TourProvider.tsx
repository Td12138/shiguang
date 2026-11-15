import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { TOUR_STEPS } from './tourSteps';
import { TourOverlay } from './TourOverlay';

/** §6.16：写入后不再自动出现；顶栏可手动重看 */
const TOUR_STORAGE_KEY = 'shiguang.tour.v1';

export interface TourApi {
  /** 重新观看：从第一步开始 */
  start: () => void;
  active: boolean;
}

const TourContext = createContext<TourApi | null>(null);

export function useTour(): TourApi {
  const ctx = useContext(TourContext);
  if (!ctx) throw new Error('useTour 必须在 <TourProvider> 内使用');
  return ctx;
}

export function TourProvider({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const [index, setIndex] = useState<number | null>(null);

  const start = useCallback((): void => setIndex(0), []);

  const finish = useCallback((): void => {
    try {
      window.localStorage.setItem(TOUR_STORAGE_KEY, 'done');
    } catch {
      // 隐私模式下写不进去也不该打断使用
    }
    setIndex(null);
  }, []);

  const goTo = useCallback(
    (next: number): void => {
      if (next < 0) return;
      if (next >= TOUR_STEPS.length) {
        finish();
        return;
      }
      setIndex(next);
    },
    [finish],
  );

  // 首次进入：等页面渲染完再起引导（避免目标元素还没挂上）
  useEffect(() => {
    let seen = false;
    try {
      seen = window.localStorage.getItem(TOUR_STORAGE_KEY) === 'done';
    } catch {
      seen = false;
    }
    if (seen) return undefined;
    const timer = window.setTimeout(() => setIndex(0), 600);
    return () => window.clearTimeout(timer);
  }, []);

  // 每一步先切到需要的路由，再由 Overlay 重新测量
  useEffect(() => {
    if (index === null) return;
    const step = TOUR_STEPS[index];
    if (step?.path) navigate(step.path);
  }, [index, navigate]);

  const api = useMemo<TourApi>(() => ({ start, active: index !== null }), [start, index]);
  const step = index === null ? null : TOUR_STEPS[index] ?? null;

  return (
    <TourContext.Provider value={api}>
      {children}
      {step && index !== null ? (
        <TourOverlay
          key={step.key}
          step={step}
          index={index}
          total={TOUR_STEPS.length}
          onNext={() => goTo(index + 1)}
          onPrev={() => goTo(index - 1)}
          onSkip={finish}
          onMissing={() => goTo(index + 1)}
        />
      ) : null}
    </TourContext.Provider>
  );
}
