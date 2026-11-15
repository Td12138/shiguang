import { Suspense } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { ErrorBoundary } from '@/components/ui/ErrorBoundary';
import { BottomTabs } from './BottomTabs';
import { RouteFallback } from './RouteFallback';
import { Sidebar } from './Sidebar';
import { TopBar } from './TopBar';
import { findNavItem } from './nav';
import styles from './AppLayout.module.css';

/** 应用外壳：侧栏 + 标题栏 + 内容区；路由内容全部懒加载 */
export function AppLayout() {
  const location = useLocation();
  const current = findNavItem(location.pathname);

  return (
    <div className={styles.shell}>
      <a className={styles.skip} href="#main-content">
        跳到正文
      </a>
      <Sidebar />
      <div className={styles.main}>
        <TopBar title={current.title} subtitle={current.subtitle} />
        <main id="main-content" className={styles.content}>
          <Suspense fallback={<RouteFallback />}>
            <ErrorBoundary key={location.pathname}>
              <Outlet />
            </ErrorBoundary>
          </Suspense>
        </main>
        <footer className={styles.footer}>
          <p>碳当量为估算，基于公开因子表；食材与浪费记录只存在本地 SQLite。</p>
        </footer>
      </div>
      <BottomTabs />
    </div>
  );
}
