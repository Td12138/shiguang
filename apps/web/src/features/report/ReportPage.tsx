import { PagePlaceholder } from '@/components/layout/PagePlaceholder';

export default function ReportPage() {
  return (
    <PagePlaceholder
      status="周报模块接入中"
      title="一周一页，边生成边出现"
      description="周报用 SSE 流式生成：先出结论，再出引用；数据不足时直说不足，不编故事。"
      capabilities={[
        '流式输出（text/event-stream），首字延迟可见',
        '生成结束后附本次引用的来源清单',
        '可导出为图片，方便发给家人或贴进周记',
      ]}
      endpoints={['POST /api/report/weekly']}
      footnote="流式渲染期间保留占位高度，避免正文跳动。"
    />
  );
}
