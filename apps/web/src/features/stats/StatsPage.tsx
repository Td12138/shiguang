import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { DemoBanner } from '@/components/ui/DemoBanner';
import { EmptyState } from '@/components/ui/EmptyState';
import { Notice } from '@/components/ui/Notice';
import { Segmented } from '@/components/ui/Segmented';
import { Skeleton } from '@/components/ui/Skeleton';
import { formatGrams, formatPercent } from '@/lib/format';
import { RANGE_OPTIONS, useStats } from './useStats';
import { StatTile } from './StatTile';
import { TrendChart } from './TrendChart';
import { WasteRing } from './WasteRing';
import styles from './StatsPage.module.css';

function EquivalentIcon({ kind }: { kind: 'car' | 'tree' | 'leaf' }) {
  if (kind === 'car') {
    return (
      <svg viewBox="0 0 32 32" aria-hidden="true" focusable="false">
        <path
          fill="currentColor"
          d="M6 13l2.4-5.2c.4-.8 1.2-1.3 2.1-1.3h11c.9 0 1.7.5 2.1 1.3L26 13c2 .5 3 1.8 3 4v5.5h-3v2h-3v-2H9v2H6v-2H3V17c0-2.2 1-3.5 3-4Z"
        />
        <path fill="var(--color-surface)" d="M9.2 13l2-4h9.6l2 4h-13.6Z" />
        <circle cx="8" cy="18" r="1.5" fill="var(--color-surface)" />
        <circle cx="24" cy="18" r="1.5" fill="var(--color-surface)" />
      </svg>
    );
  }

  if (kind === 'tree') {
    return (
      <svg viewBox="0 0 32 32" aria-hidden="true" focusable="false">
        <path
          fill="currentColor"
          d="M16 3a7 7 0 0 0-6.6 9.2A5.5 5.5 0 0 0 11 23h10a5.5 5.5 0 0 0 1.6-10.8A7 7 0 0 0 16 3Z"
        />
        <path fill="currentColor" d="M14 20h4v9h-4z" />
        <path
          d="M16 12v10m0-5-4-3m4 5 4-3"
          fill="none"
          stroke="var(--color-surface)"
          strokeLinecap="round"
          strokeWidth="1.5"
        />
      </svg>
    );
  }

  return (
    <svg viewBox="0 0 32 32" aria-hidden="true" focusable="false">
      <path fill="currentColor" d="M27 4C15 4 7 8.5 7 17.5 7 23 10.5 27 16 27c9 0 12-11 11-23Z" />
      <path
        d="M9 25 23 9m-9 11h6m-3-3v-5"
        fill="none"
        stroke="var(--color-surface)"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.6"
      />
    </svg>
  );
}

export default function StatsPage() {
  const stats = useStats();
  const data = stats.data;
  const hasData = data !== null && data.saved_grams + data.thrown_grams > 0;

  return (
    <div className="page-stack">
      {stats.demo ? (
        <DemoBanner
          message="统计接口没有响应，下面的数字是内置样例，不是你真实的浪费记录。"
          onRetry={() => void stats.reload()}
        />
      ) : null}

      <Card
        className={styles.summaryCard}
        title="这段时间的账本"
        subtitle="每一次吃完和丢弃，都有记录"
        actions={
          <div className={styles.controls}>
            <Segmented
              ariaLabel="统计区间"
              options={RANGE_OPTIONS}
              value={stats.range}
              onChange={stats.setRange}
              disabled={stats.loading}
            />
            <Button variant="ghost" size="sm" onClick={() => void stats.reload()} loading={stats.loading}>
              刷新
            </Button>
          </div>
        }
      >
        {stats.loading ? (
          <div className={styles.summary}>
            <Skeleton height="284px" radius="var(--radius-md)" />
            <div className={styles.loadingStack}>
              <Skeleton height="88px" radius="var(--radius-md)" />
              <Skeleton height="56px" radius="var(--radius-sm)" />
              <Skeleton height="56px" radius="var(--radius-sm)" />
              <Skeleton height="56px" radius="var(--radius-sm)" />
            </div>
          </div>
        ) : stats.error ? (
          <Notice tone="error" title="读取失败">
            {stats.error}
          </Notice>
        ) : !hasData ? (
          <EmptyState
            tone="inline"
            title="这个区间还没有记录"
            description="做过一次菜或丢过一次东西后，这里才会有数字。先去「今日吃啥」做一顿吧。"
          />
        ) : data ? (
          <div className={styles.summary}>
            <div className={styles.ring}>
              <span className={styles.ringTitle}>食材去向</span>
              <WasteRing
                wasteRate={data.waste_rate}
                savedGrams={data.saved_grams}
                thrownGrams={data.thrown_grams}
              />
              <p className={styles.ringFormula}>浪费率 = 丢弃 ÷（丢弃 + 吃掉）</p>
            </div>
            <div className={styles.overview}>
              <div className={styles.savings}>
                <span className={styles.savingsLabel}>这段时间，省下的食材钱</span>
                <p className={styles.savingsValue}>
                  <span>¥</span>
                  {data.money_saved}
                </p>
                <span className={styles.savingsHint}>按已吃掉食材的均价折算</span>
              </div>
              <div className={styles.metrics}>
                <StatTile
                  label="少扔了"
                  value={formatGrams(data.saved_grams)}
                  hint="已经吃掉的食材，按克数计"
                  tone="good"
                />
                <StatTile
                  label="扔掉了"
                  value={formatGrams(data.thrown_grams)}
                  hint="记入浪费账的丢弃重量"
                  tone="bad"
                />
                <StatTile
                  label="少排碳"
                  value={`${data.carbon_saved_kg}`}
                  unit="kg CO₂e"
                  hint="按食材碳因子估算"
                />
              </div>
            </div>
          </div>
        ) : null}
      </Card>

      {data && hasData ? (
        <>
          <Card
            className={styles.equivalentsCard}
            title="换算成日常，更直观"
            subtitle="这些数字，大约相当于下面的生活尺度"
          >
            <div className={styles.equivalents}>
              <div className={styles.equivalent}>
                <span className={styles.eqIcon}>
                  <EquivalentIcon kind="car" />
                </span>
                <span className={styles.eqValue}>{data.equivalents.car_km}</span>
                <span className={styles.eqLabel}>公里不用开车</span>
                <span className={styles.eqHint}>
                  按 {data.factors?.car_kg_per_km ?? 0.137} kg CO₂e / 公里估算
                </span>
              </div>
              <div className={styles.equivalent}>
                <span className={styles.eqIcon}>
                  <EquivalentIcon kind="tree" />
                </span>
                <span className={styles.eqValue}>{data.equivalents.trees_days}</span>
                <span className={styles.eqLabel}>棵树一天的吸收量</span>
                <span className={styles.eqHint}>
                  按 {data.factors?.tree_kg_per_day ?? 0.0438} kg CO₂e / 树·天估算
                </span>
              </div>
              <div className={styles.equivalent}>
                <span className={styles.eqIcon}>
                  <EquivalentIcon kind="leaf" />
                </span>
                <span className={styles.eqValue}>{formatPercent(data.waste_rate, 1)}</span>
                <span className={styles.eqLabel}>本期浪费率</span>
                <span className={styles.eqHint}>越低越好，0% 表示这段没扔过东西</span>
              </div>
            </div>
          </Card>

          <Card
            className={styles.trendCard}
            title="每日趋势"
            subtitle={data.range ? `区间 ${data.range}：吃掉与扔掉按天对照` : '吃掉与扔掉按天对照'}
          >
            {data.trend.length === 0 ? (
              <EmptyState tone="inline" title="区间内还没有按天的记录" description="记录几天之后，这里会出现柱状趋势。" />
            ) : (
              <TrendChart points={data.trend} />
            )}
          </Card>
        </>
      ) : null}

      <Notice tone="info" title="口径与免责">
        所有数字都是<strong>估算</strong>：碳当量基于公开因子表，克数由数量 × 平均重量推算，金额按食材均价折算。
        因子来源与计算方式见项目文档《数据来源与合规》。
      </Notice>
    </div>
  );
}
