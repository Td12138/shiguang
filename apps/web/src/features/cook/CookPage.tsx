import { PagePlaceholder } from '@/components/layout/PagePlaceholder';

export default function CookPage() {
  return (
    <PagePlaceholder
      status="菜谱模块接入中"
      title="选食材，换一顿饭"
      description="AI 先读临期库存，再检索菜谱，给出理由、缺料提示与可回看的引用；没有匹配时明确说没有。"
      capabilities={[
        '按临期程度推荐，先消耗快坏的',
        '缺料必买与可选配料分开展示',
        '每条结论挂引用角标，点击看原文',
        '展开 Agent 步骤时间线，复现推理过程',
      ]}
      endpoints={['POST /api/recipes/suggest', 'GET /api/agent/runs/{id}']}
      footnote="菜谱只是消耗手段，主轴始终是过期倒计时。"
    />
  );
}
