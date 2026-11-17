import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { DemoBanner } from '@/components/ui/DemoBanner';
import { Notice } from '@/components/ui/Notice';
import { Skeleton } from '@/components/ui/Skeleton';
import { formatGrams, formatPercent } from '@/lib/format';
import { CitationList } from './CitationList';
import { useWeeklyReport } from './useWeeklyReport';
import styles from './ReportPage.module.css';

const STATUS_LABEL = {
  idle: '等待生成',
  streaming: '正在生成',
  done: '已生成',
  error: '生成中断',
} as const;

function ReportIllustration() {
  return (
    <svg viewBox="0 0 230 180" aria-hidden="true" focusable="false">
      <circle cx="121" cy="91" r="76" fill="#f3d9bf" />
      <path d="M41 139c34-19 83-20 145-2" fill="none" stroke="#b7c8ac" strokeLinecap="round" strokeWidth="5" />
      <g transform="rotate(5 119 88)">
        <rect x="58" y="21" width="126" height="137" rx="12" fill="#d8c9af" opacity=".35" />
        <rect x="52" y="15" width="126" height="137" rx="12" fill="#fffdf8" />
        <rect x="88" y="7" width="54" height="19" rx="6" fill="#e4572e" />
        <path d="M70 45h76M70 59h54" stroke="#d8c9af" strokeLinecap="round" strokeWidth="6" />
        <circle cx="88" cy="98" r="22" fill="none" stroke="#e3dac9" strokeWidth="9" />
        <path d="M88 76a22 22 0 0 1 19 32" fill="none" stroke="#5b8c5a" strokeLinecap="round" strokeWidth="9" />
        <path d="M122 87h37M122 101h29M122 115h35M70 133h88" stroke="#d8c9af" strokeLinecap="round" strokeWidth="5" />
      </g>
      <g transform="rotate(-37 184 119)">
        <rect x="178" y="78" width="13" height="79" rx="5" fill="#e4572e" />
        <path d="M178 151h13l-6.5 14Z" fill="#8f3716" />
        <path d="M178 84h13" stroke="#fffdf8" strokeWidth="3" />
      </g>
      <path d="M39 48c16-3 24-12 26-27-16 2-25 11-26 27Z" fill="#5b8c5a" />
      <path d="M42 44 60 27" stroke="#fffdf8" strokeLinecap="round" strokeWidth="2" />
    </svg>
  );
}

export default function ReportPage() {
  const report = useWeeklyReport();
  const fallback = report.fallback;

  return (
    <div className="page-stack">
      {report.fallbackDemo ? (
        <DemoBanner message="周报接口没有响应，下面是内置样例统计摘要，不是你的真实记录。" />
      ) : null}

      <section className={styles.hero} aria-labelledby="report-hero-title">
        <div className={styles.heroCopy}>
          <span className={styles.kicker}>食光 · 厨房周记</span>
          <h2 id="report-hero-title">从冰箱，到餐桌。</h2>
          <p>根据近 30 天的吃掉与丢弃记录生成，数字和结论都能回看来源。</p>
          <div className={styles.heroActions}>
            <Button
              onClick={() => void report.start()}
              loading={report.status === 'streaming'}
              disabled={report.status === 'streaming'}
            >
              {report.status === 'idle' ? '生成本周周报' : '重新生成'}
            </Button>
            <span className={styles.rangeNote}>
              <svg viewBox="0 0 20 20" aria-hidden="true">
                <rect x="3" y="4.5" width="14" height="12" rx="3" fill="currentColor" />
                <path d="M6 2.8v3M14 2.8v3M3.8 8h12.4" stroke="#e8efe1" strokeLinecap="round" strokeWidth="1.5" />
              </svg>
              近 30 天记录
            </span>
          </div>
        </div>
        <div className={styles.heroArt}>
          <ReportIllustration />
        </div>
      </section>

      <Card className={styles.paper}>
        <article>
          <header className={styles.articleHeader}>
            <div>
              <span className={styles.articleKicker}>本周记录</span>
              <h2 className={styles.articleTitle}>本周周报</h2>
            </div>
            <span className={styles.status} data-status={report.status}>
              <i aria-hidden="true" />
              {STATUS_LABEL[report.status]}
            </span>
          </header>

          {report.status === 'streaming' && report.text.length === 0 ? (
            <div className={styles.loading}>
              <Skeleton lines={3} height="16px" />
              <p className={styles.loadingHint}>正在读取统计并生成…</p>
            </div>
          ) : null}

          {report.text.length > 0 ? (
            <div className={styles.stream} aria-live="polite" aria-busy={report.status === 'streaming'}>
              {report.text.split('\n').map((line, index, lines) => (
                <p
                  key={`${index}-${line.slice(0, 8)}`}
                  className={`${styles.paragraph} ${index === 0 ? styles.leadParagraph : ''}`}
                >
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
        </article>
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
            <section className={styles.fallback} aria-labelledby="fallback-title">
              <h2 id="fallback-title">近 30 天统计摘要</h2>
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
            </section>
          ) : (
            <Skeleton height="88px" radius="var(--radius-md)" />
          )}
        </>
      ) : null}

      <Notice tone="info" title="关于这份周报">
        生成时会逐字显示；结束后附上引用清单，方便核对数字来源。数据不足时，周报也会如实说明。
      </Notice>
    </div>
  );
}
