import { PagePlaceholder } from '@/components/layout/PagePlaceholder';

export default function StatsPage() {
  return (
    <PagePlaceholder
      status="统计模块接入中"
      title="这本账只记一件事：少扔了多少"
      description="浪费率、少扔克数、省下的钱与碳当量，按周或按月汇总，口径与公式都能对上。"
      capabilities={[
        '浪费率 = 丢弃 /（丢弃 + 吃掉）',
        '少扔克数、省下的钱分别统计',
        '碳当量换算为等效开车里程与树木吸收天数',
        '每日趋势：扔掉的与吃掉的对照',
      ]}
      endpoints={['GET /api/stats/summary?range=30d']}
      footnote="碳当量为估算，基于公开因子表；页面会标注估算口径，不做精确承诺。"
    />
  );
}
