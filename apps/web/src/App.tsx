import { lazy } from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AppLayout } from './components/layout/AppLayout';
import { ErrorBoundary } from './components/ui/ErrorBoundary';
import { ToastProvider } from './components/ui/Toast';

// 路由级懒加载：首屏只加载外壳 + 首页，其余页面按需拉取
const DashboardPage = lazy(() => import('./features/dashboard/DashboardPage'));
const CapturePage = lazy(() => import('./features/capture/CapturePage'));
const CookPage = lazy(() => import('./features/cook/CookPage'));
const StatsPage = lazy(() => import('./features/stats/StatsPage'));
const ReportPage = lazy(() => import('./features/report/ReportPage'));

export default function App() {
  return (
    <ErrorBoundary title="应用没能启动">
      <ToastProvider>
        <BrowserRouter>
          <Routes>
            <Route element={<AppLayout />}>
              <Route path="/" element={<DashboardPage />} />
              <Route path="/capture" element={<CapturePage />} />
              <Route path="/cook" element={<CookPage />} />
              <Route path="/stats" element={<StatsPage />} />
              <Route path="/report" element={<ReportPage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </ToastProvider>
    </ErrorBoundary>
  );
}
