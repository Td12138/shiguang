# CHANGELOG · 食光

> 只记「改变了什么 + 为什么 + 证据在哪」。产品与需求都在迭代，**文档在最后统一写**（`docs/04` 技术文档、视频脚本、答辩材料定稿留到提交前 12 小时），过程中靠本文件与 Git 历史留痕。

## 2026-11-15（省赛交付版）

### 新增
- **交付文档**：`docs/04-技术方案.md`（10 章，含 AI 六项、业务正确性、测试实测、部署、局限）与 `docs/05-演示视频分镜.md`（7:05 分镜、逐段口播、拍前清单与分段复位）
- **小票识别**：`POST /api/capture/receipt`，拍小票/外卖单批量入库（借自 FridgeMate、FridgeVision 的「购物后自动登记」思路）
- **备菜流水线**：`POST /api/cook/sequence`，多道菜的并行烹饪时间轴（借自 cooking-agent 的「备菜流水线」）
- **饮食计划**：`POST /api/plan/meals`，3 天配餐 + 覆盖统计 + 采购清单；五步 Agent（understand→plan→allocate→compose→verify）
  - 证据：`apps/server/app/domain/plan.py`、`tests/test_plan.py`；实测 3 天计划、`coverage {used_items:6, expiring_used:3}`
- **对话改计划**：`POST /api/plan/meals/{plan_id}/revise`，只重排受影响餐次并返回 `changed` diff
- **偏好记忆**：`preferences` 表 + `/api/preferences` 增删查；偏好同步进 FTS，`avoid` 为硬约束、`confidence<0.6` 不生效
- 前端新增 `/plan` 页与「我的偏好」面板；计划页常驻改计划输入框

### 修复（第三轮审查）
- **阻塞**：忌口 `avoid` 在「食材本来就不在库存」时整条失效 → 改为从偏好文本直接抽词（`不吃鸡蛋`→`鸡蛋`），并独立校验
- 同名多批库存只按最后一批算 → `_split_inventory` 合并数量与克数
- 上传目录写进发布目录、切软链后丢失 → 新增 `SHIGUANG_UPLOAD_DIR`，部署指向 `shared/upload`
- 对账 apply 中途失败留半截数据 / 幂等台账误伤后续合法动作 / `checked_at` 未校验可抹掉新鲜度提示 → 见下轮修复
- 改计划未涉及餐次 `uses`/`shopping` 漂移、指名菜不生效却报成功 → 见下轮修复

### 修复（第二轮审查提出）
- mock 与真实 provider 语义不一致：schema 校验失败直接返回候选值 → 改为「校验→重试 1 次→明确报错」
- mock 内置菜谱 id/标题与 `recipes.json` 错配 → 对齐 r_002/r_001/r_003
- 真实 VLM 三种返回姿势（裸数组 / `{items:[...]}` / 套娃）→ 递归拍平
- 本机 TLS 代理导致 `certifi` 间歇校验失败 → `SHIGUANG_SSL_VERIFY=os|strict|off`
- 非本地 provider 缺 key 时仍真发请求 → 启动即回退 mock 并告警
- 上传上限三处不一致（8/15/5 MB）→ 收敛到 `config.MAX_UPLOAD_BYTES`
- 404/422 返回体不统一 → 统一 `{code,message,detail?}`，且 `/api/*` 不再回退成 index.html
- 健康检查连接未关闭 → 显式 close；`ok` 与 db 状态联动

### 竞品借鉴（GitHub 调研，2026-11-15）

调研范围：`fridge food waste`、`food inventory app`、`食材管理`、`recipe rag llm`、`meal planner ai` 五组关键词，共看 20+ 仓库，代表性项目：FridgeMate_AI、FridgeVision(FreshTrackAI)、fridge_guardian(冰箱守卫者)、AIrecipe、cooking-agent、nishiki、home-inventory、AI-Meal-Planner。

| 借鉴点 | 出处 | 我们的处理 |
|---|---|---|
| 小票/订单批量登记 | FridgeMate、FridgeVision | ✅ 新增 `/api/capture/receipt`，复用 VLM + 别名表 |
| 备菜流水线（并行时间轴） | cooking-agent | ✅ 新增 `/api/cook/sequence` |
| 定时巡检 + 主动提醒 | fridge_guardian（Spring Task） | ⏳ 前端通知 + 首页 digest（本轮做） |
| 分类 + 存放位置（冷藏/冷冻/常温） | fridge_guardian、home-inventory | ⏳ 分类已补；位置字段按需再加 |
| 红黄绿徽章 + 「明天过期/已过期 2 天」文案 | fridge_guardian | ✅ 已有分级，文案沿用 |
| 浪费率饼图 / 消费看板 | fridge_guardian、AIrecipe | ✅ 已有（手写 SVG，不引图表库） |
| 扫码条码入库 | PlateSwipe | ❌ 放弃：中文商品条码库成本高，VLM 拍小票更通用 |
| 摄像头常驻自动登记 | FridgeVision | ❌ 放弃：需要硬件与常开设备，省赛演示不现实 |
| 用户认证 / JWT / 多用户 | fridge_guardian、merran | ❌ 放弃：单人本地应用，认证不产生评分收益，反而拖工期 |
| 营养/热量分析 | AI-Meal-Planner | ❌ 放弃：医疗口径风险高，评审一问「依据是什么」就崩 |

### 决策记录（带理由）

| 决策 | 理由 |
| 识别结果不直接入库，必须人工确认 | 模型会错（实测数量返回 null、置信度虚高为 1.0），承认错误比假装准确更可信 |
| 降级放业务层，模型层只负责「成功或明确失败」 | 避免「AI 挂了却假装成功」，这是安全可控性的实证点 |
| 过期食材绝不进推荐/计划，只提示处理 | 食品安全底线，且能演示「规则硬约束不是提示词祈祷」 |
| 偏好必须可删除、低置信度不生效 | AI 推断会错，用户要能推翻；也是答辩必问点 |
| 部署不装 nginx，FastAPI 托管静态 | 云端 1.6 GB 内存，少一个进程少一个故障点 |
| 公网演示加 Basic Auth + 限流，默认关闭 | 挂公网且能调模型，不加防护等于送 key；开关默认关闭保证本地开发行为不变 |

## 2026-11-15

- `0495c1a` 之前：选题对比（家书 / 碳账本 / 政策通 / 说明书管家），最终选剩食管家——理由是「输入是一张照片」，演示不依赖冷启动数据
- 规划：省赛 72 小时倒排、提交物清单、部署方案（cloudserver200m）
- 契约定稿：API / 表结构 / 目录所有权 / 计量口径，作为多代理并行的唯一对齐物
- 并行交付：后端基础设施、RAG 与业务域、前端骨架、种子数据、提交材料
- 第一轮独立审查：产出 30+ 条缺陷，修完阻塞与重要项
- 真实 VLM 接入实测：`glm-4v-flash`，冰箱实景 4 项、4.98 s

## 提交物进度

| 项 | 状态 |
|---|---|
| 代码仓库 | ✅ 已推 GitHub `Td12138/shiguang`（41 个细粒度提交；提交时转 public 或提供评审访问） |
| README / 环境说明 | ✅ |
| LICENSE / 第三方清单 | ✅ |
| 在线 Demo | ✅ `http://47.100.224.209:8720`（Basic 认证，mock 模式） |
| 技术文档 PDF ≤30 页 | ⏳ 正在写（docs/04） |
| 演示视频 5–8 min | ⏳ 脚本定稿中（docs/05），需自备素材录制 |
