# CHANGELOG · 食光

> 只记「改变了什么 + 为什么 + 证据在哪」。产品与需求都在迭代，**文档在最后统一写**（`docs/04` 技术文档、视频脚本、答辩材料定稿留到提交前 12 小时），过程中靠本文件与 Git 历史留痕。

## 2026-11-17（UI 改版合并 + 独立审查修复）

### 新增
- **暖阳厨房主题**（合并 `feat/ui-warm-kitchen`，`463fd63`）：暖纸底 + 柑橘橙行动色 + 深厨绿结构色；双色填充导航/分类图标；首页 hero 主视觉、周报「厨房周记」版式、统计页生活尺度换算卡。

### 修复（两轮独立子代理审查）
- **P0 · public 根级资源被 SPA 回退吞掉**：FastAPI 只挂 `/assets`，`/logo.svg`、`/hero-kitchen.jpg` 全返回 index.html（`text/html`）→ 线上侧栏碎图、首页 hero 无图。新增 `app/core/webdist.py` 统一解析 dist 内真实文件（含目录穿越防护），SPA 回退只对不存在的路径生效；`/assets/*` immutable 长缓存、公共文件 1 h、index.html `no-cache`；限流豁免复用同一解析。证据：`tests/test_static.py` 6 项；本地实测 `/logo.svg → image/svg+xml`、`/hero-kitchen.webp → image/webp 43 KB`、`/stats → index.html + no-cache`。
- **P1 · 对比度**：faint `#9c9081`(2.6–3.1) → `#75685a`(≥4.5)；主色当文字的场景统一 `--color-primary-text #b8431f`；主按钮底 `--color-primary-strong #c0431f`（白字 4.83）；danger/warn/fresh 语义色按「文字也够读」重定值；侧栏深底半透明白字 55%/50% → 75%（6.2）。
- **P1 · 768–1024px 断点塌陷**：统计页「换算成日常」三列在 900px 时文字列只剩 34px → ≤1000px 改竖排清单；周报 hero 文案列被按钮最小宽度顶破 → ≤1024px 插画列收窄到 140px + `.heroCopy{min-width:0}`；首页 hero 文案列 ≤1024px 放宽到 68%。
- **P2**：`NavIcon` 根节点残留 `stroke="currentColor"` 给填充块套描边 → `stroke="none"`；两处死 class 引用（`styles.summaryCard` / `styles.article`）删除；环图图例补回克数；金额用 `formatAmount` 固定两位小数；`--font-display` 补回 Segoe UI（Windows 数字字形一致）。

### 优化
- **图表不只靠色相**：趋势柱「扔掉」用 SVG `<pattern>` 斜纹、环图「扔掉」弧叠斜纹刻度，图例同步斜纹色块；灰度/色盲可分辨。
- **首页 hero 瘦身**：2560px/235 KB → 1600px JPEG 87 KB + WebP 42 KB，CSS `image-set()` 优先 WebP、JPEG 回退（原图备份 `temp/shiguang-review/`）。
- **favicon 独立**：`favicon.svg` 带深厨绿圆角底（浅色标签栏可见），侧栏仍用透明底 `logo.svg`。
- **令牌收敛**：新增 on-teal 系列 / hero / skeleton / thrown / eaten / fresh-border 等令牌，替换组件内重复硬编码色；删除零引用的 `--color-teal-soft`。
- **周报模板说人话**：`30d` → 「近 30 天」，克数 ≥1 kg 用 kg 一位小数（与前端 `formatGrams` 同口径），金额两位小数。

### 测试
- 后端 **147 passed**（141 + 6 项静态托管回归），约 28 s；前端 `pnpm typecheck` 0 error、`pnpm build` 225 modules。
- 视觉取证：Playwright 桌面 1440 / 平板 900 / 移动 390 三档 × 6 页，`overflowX=0`、console error=0（截图 `temp/shiguang-review/shots3/`）。

## 2026-11-15（省赛交付版）

### 修复（交付前独立审查，2026-11-15 晚）
- 后端：限流移到认证前并按静态/健康路径豁免；非 ASCII Basic 头返回 401 而不是 500；capture 空结果不再回填 fixture、缺数量不再静默当 1.0；mock 周报改用当前统计模板；5 个工具 schema 与签名对齐；对账去掉名称互含、并发 `request_id` 用事务内 fingerprint 原子占位；MCP 启动自动建库。
- 前端：「做了」按 `uses[].qty` 折克扣减，不再整条扣库存；Button loading 时禁用并加提交锁；首页卡片新增改数量/到期日与“扔了”；对账“全部保留”写回原数量；计划页 429 显示错误+重试；周报断流检测；trace 按 runId 重置；改名后不再携带旧 `item_id`。
- 部署：`deploy.ps1` 增加 pnpm install、构建失败中断、发布权限收紧、`shiguang` 专用用户、health 门失败自动回滚；`install.sh` 修正软链顺序与 `.env` 权限；systemd 加固；新增 `deploy/harden-existing.sh`。
- 文档/PDF：提交数与失效 hash 校正；公开仓库内部文档去掉“不对外/完整可抄/mock 直接失分”等自伤表述；数据来源/CC BY/字体许可按实际改写；PDF 修复 `≤ ∈ ≈ ①②③` 缺字、目录“5.1 5.1”、测试数 141。
- 测试：110 项业务测试 + 31 项审查回归 = **141 passed**。

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

- 立项前：选题对比（家书 / 碳账本 / 政策通 / 说明书管家），最终选剩食管家——理由是「输入是一张照片」，演示不依赖冷启动数据（讨论稿见 `docs/01`、`docs/02`）
- 规划：省赛 72 小时倒排、提交物清单、部署方案（cloudserver200m）
- 契约定稿：API / 表结构 / 目录所有权 / 计量口径，作为多代理并行的唯一对齐物
- 并行交付：后端基础设施、RAG 与业务域、前端骨架、种子数据、提交材料
- 第一轮独立审查：产出 30+ 条缺陷，修完阻塞与重要项
- 真实 VLM 接入实测：`glm-4v-flash`，冰箱实景 4 项、4.98 s

## 提交物进度

| 项 | 状态 |
|---|---|
| 代码仓库 | ✅ 已推 GitHub `Td12138/shiguang`（截至 11-15 18:12 为 49 个细粒度提交；之后审查修复提交见 `git log`） |
| README / 环境说明 | ✅ |
| LICENSE / 第三方清单 | ✅ |
| 在线 Demo | ✅ `http://47.100.224.209:8720`（Basic 认证，mock 模式） |
| 技术文档 PDF ≤30 页 | ✅ 已出（`outputs/chuanzhi-aiweb/食光-技术文档.pdf`，A4 15 页，LaTeX 排版，含封面/目录/页脚页码） |
| 演示视频 5–8 min | ⏳ 脚本定稿（docs/05，7:05），待录制 |
