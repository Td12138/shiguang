import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { DemoBanner } from '@/components/ui/DemoBanner';
import { Notice } from '@/components/ui/Notice';
import { Skeleton } from '@/components/ui/Skeleton';
import { formatGrams, formatPercent } from '@/lib/format';
import { CitationList } from './CitationList';
import { useWeeklyReport } from './useWeeklyReport';
import styles from './ReportPage.module.css';

export default function ReportPage() {
  const report = useWeeklyReport();
  const fallback = report.fallback;

  return (
    <div className="page-stack">
      {report.fallbackDemo ? (
        <DemoBanner message="周报接口没有响应，下面是内置样例统计摘要，不是你的真实记录。" />
      ) : null}

      <Card
        title="本周周报"
        subtitle="流式生成：先出结论，再给引用；数据不足时直说不足"
        actions={
          <Button
            variant="secondary"
            size="sm"
            onClick={() => void report.start()}
            loading={report.status === 'streaming'}
            disabled={report.status === 'streaming'}
          >
            {report.status === 'idle' ? '生成本周周报' : '重新生成'}
          </Button>
        }
      >
        {report.status === 'streaming' && report.text.length === 0 ? (
          <div className={styles.loading}>
            <Skeleton lines={3} height="16px" />
            <p className={styles.loadingHint}>正在读取统计并生成…</p>
          </div>
        ) : null}

        {report.text.length > 0 ? (
          <div className={styles.stream} aria-live="polite" aria-busy={report.status === 'streaming'}>
            {report.text.split('\n').map((line, index, lines) => (
              <p key={`${index}-${line.slice(0, 8)}`} className={styles.paragraph}>
                {line}
                {report.status === 'streaming' && index === lines.length - 1 ? (
                  <span className={styles.cursor} aria-hidden="true" />
                ) : null}
              </p>
            ))}
          </div>
        ) : null}

        {report.status === 'done' && report.citations.length > 0 ? (
          <CitationList items={report.citations} />
        ) : null}

        {report.status === 'error' && report.text.length === 0 ? (
          <p className={styles.interrupted}>
            流式输出中断，这次没有生成正文；下面是同一区间的统计摘要，可直接当周报读。
          </p>
        ) : null}

        {report.status === 'done' ? (
          <p className={styles.footnote}>
            周报内容由模型生成，数字来自本地统计；碳当量为估算，引用可点击回看来源。
          </p>
        ) : null}
      </Card>

      {report.status === 'error' ? (
        <>
          <Notice
            tone="error"
            title="生成失败，已给出统计摘要"
            action={
              <Button variant="secondary" size="sm" onClick={() => void report.start()}>
                重试生成
              </Button>
            }
          >
            {report.error ?? '流式接口没有响应'}；下面是同一区间（近 30 天）的统计，可直接作为周报正文。
          </Notice>

          {fallback ? (
            <div className={styles.fallbackGrid}>
              <div className={styles.fallbackItem}>
                <span className={styles.fallbackLabel}>浪费率</span>
                <span className={styles.fallbackValue}>{formatPercent(fallback.waste_rate, 1)}</span>
              </div>
              <div className={styles.fallbackItem}>
                <span className={styles.fallbackLabel}>吃掉</span>
                <span className={styles.fallbackValue}>{formatGrams(fallback.saved_grams)}</span>
              </div>
              <div className={styles.fallbackItem}>
                <span className={styles.fallbackLabel}>扔掉</span>
                <span className={styles.fallbackValue}>{formatGrams(fallback.thrown_grams)}</span>
              </div>
              <div className={styles.fallbackItem}>
                <span className={styles.fallbackLabel}>少排碳</span>
                <span className={styles.fallbackValue}>{fallback.carbon_saved_kg} kg</span>
              </div>
            </div>
          ) : (
            <Skeleton height="88px" radius="var(--radius-md)" />
          )}
        </>
      ) : null}

      <Notice tone="info" title="关于流式">
        输出过程中会一直显示光标；结束后才附引用清单，避免「先给结论、没有出处」。
      </Notice>
    </div>
  );
}
