import { PagePlaceholder } from '@/components/layout/PagePlaceholder';

export default function CapturePage() {
  return (
    <PagePlaceholder
      status="识别模块接入中"
      title="拍一张冰箱照片"
      description="上传后由视觉模型识别食材与置信度，结果先进入可校对清单，确认之后才写进库存。"
      capabilities={[
        '拍照或拖拽上传，单张即可',
        '逐项校对名称、数量、单位与到期日',
        '置信度低于 70% 的条目自动标黄并说明原因',
        '识别结果不入库、不扣库存，确认才生效',
      ]}
      endpoints={['POST /api/capture/recognize', 'POST /api/inventory']}
      footnote="识别结果永远需要人工确认——这是本项目的安全底线，也是与竞品最大的差别。"
    />
  );
}
