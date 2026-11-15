/** §6.13 对账结果的内置样例（识别接口不通时演示；apply 永远走真实接口） */
import type { ReconcileResult } from './types-reconcile';

export const MOCK_RECONCILE: ReconcileResult = {
  image_id: 'img_reconcile_demo',
  checked_at: new Date().toISOString(),
  missing: [
    { inventory_id: 'inv_demo_02', name: '菠菜', qty: 1, unit: '把', days_left: 0 },
    { inventory_id: 'inv_demo_06', name: '番茄', qty: 2, unit: '个', days_left: 5 },
  ],
  reduced: [
    { inventory_id: 'inv_demo_07', name: '鸡蛋', from_qty: 6, to_qty: 2, unit: '个' },
    { inventory_id: 'inv_demo_04', name: '牛奶', from_qty: 1, to_qty: 1, unit: '盒' },
  ],
  added: [
    { name: '酸奶', qty: 2, unit: '杯', confidence: 0.83, matched: true },
    { name: '蓝莓', qty: 1, unit: '盒', confidence: 0.61, matched: false },
  ],
  suspect: [{ inventory_id: 'inv_demo_05', name: '香菇', reason: '外观异常/无法看清' }],
  warnings: ['演示数据：对账接口没有响应，下面的差异来自内置样例，应用不会生效'],
};
