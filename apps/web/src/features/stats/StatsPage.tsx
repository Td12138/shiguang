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
        title="区间汇总"
        subtitle="统计口径：浪费率 = 丢弃 ÷（丢弃 + 吃掉），全部按克数计"
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
          <div className={styles.grid}>
            <Skeleton height="188px" radius="var(--radius-md)" />
            <Skeleton height="88px" radius="var(--radius-md)" />
            <Skeleton height="88px" radius="var(--radius-md)" />
            <Skeleton height="88px" radius="var(--radius-md)" />
            <Skeleton height="88px" radius="var(--radius-md)" />
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
          <div className={styles.grid}>
            <div className={styles.ring}>
              <WasteRing
                wasteRate={data.waste_rate}
                savedGrams={data.saved_grams}
                thrownGrams={data.thrown_grams}
              />
            </div>
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
            <StatTile
              label="省下的钱"
              value={`¥${data.money_saved}`}
              hint="吃掉部分的等价金额"
            />
          </div>
        ) : null}
      </Card>

      {data && hasData ? (
        <>
          <Card title="等效换算" subtitle="把碳当量翻译成日常能感知的量">
            <div className={styles.equivalents}>
              <div className={styles.equivalent}>
                <span className={styles.eqValue}>{data.equivalents.car_km}</span>
                <span className={styles.eqLabel}>公里不用开车</span>
                <span className={styles.eqHint}>按 0.15 kg CO₂e / 公里估算</span>
              </div>
              <div className={styles.equivalent}>
                <span className={styles.eqValue}>{data.equivalents.trees_days}</span>
                <span className={styles.eqLabel}>棵树一天的吸收量</span>
                <span className={styles.eqHint}>按 0.06 kg CO₂e / 树·天估算</span>
              </div>
              <div className={styles.equivalent}>
                <span className={styles.eqValue}>{formatPercent(data.waste_rate)}</span>
                <span className={styles.eqLabel}>浪费率</span>
                <span className={styles.eqHint}>越低越好，0% 表示这段没扔过东西</span>
              </div>
            </div>
          </Card>

          <Card
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
