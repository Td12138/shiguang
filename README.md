# 食光 · 剩食管家

> 拍一张冰箱照片，几秒内知道**什么快坏了、今天做什么吃**；月底看到自己少扔了多少食物、少排了多少碳。（真实 VLM 实测约 5 秒，不是营销承诺）

2026 第九届传智杯全国大学生数智创新与 AI 应用大赛 · AI WEB 网页开发挑战赛（省赛作品）

**在线演示**：<http://47.100.224.209:8720>（Basic 认证，口令见交付说明；mock 模式，2026-12-31 下线）

> **免责声明**：本项目为竞赛演示作品。食材保质期、碳排因子、价格与克重均为公开资料整理的**估算值**，不构成食品安全、营养、医疗或投资建议；食材是否可食请以感官判断为准。详细口径与误差见 `docs/06-数据来源与合规.md`。

---

## 1. 它解决什么

菜谱 App 解决「我想吃什么」，没人管「我冰箱里什么快坏了、今天必须吃掉什么」。冰箱深处的叶菜、开封的酸奶、买多的豆腐，最后都进了垃圾桶。

食光把流程倒过来：**先管时效，再谈菜谱**。

| 步骤 | 做什么 | AI 在哪 |
|---|---|---|
| 1 拍 | 冰箱照片上传 | 视觉模型识别食材 + 置信度，结果**必须人工确认**后才入库 |
| 2 管 | 按剩余天数排序，红/黄/绿三级 | 对照食材库补齐保质期、碳因子、单价 |
| 3 吃 | 选临期食材 → 推荐菜谱 / 生成 3 天配餐 | 混合检索 + 五步 Agent（含引用与自检） |
| 4 记 | 「做了」扣库存、「扔了」记浪费 | 按公开因子表折算碳当量 |
| 5 看 | 浪费率、少扔克数、等效换算、周报 | 流式生成周报 + 引用 |

## 2. 三个关键设计

1. **识别不直接入库**：低置信度标黄、库外食材标 `matched:false`，人工改完才写库。模型会错，界面要承认。
2. **每个结论带出处**：菜谱推荐与配餐都返回 `citations`（来源 + 步骤定位），点角标能看原文；检索不到就明说，不编。
3. **AI 挂了要看得见**：模型不可用时降级为规则版并在页面顶部提示「已降级」，不静默假装成功。无 API key 时用 `mock` 回放跑通全链路，便于评审核对。

**界面**：暖阳厨房主题（暖纸底 + 柑橘橙行动色 + 深厨绿结构色），手写 CSS 变量设计系统与 SVG 图表，不引 UI 库/图表库；颜色按用途分档保证正文对比度 ≥4.5:1，图表「吃掉/扔掉」另叠斜纹而不只靠色相；390–1440 四档断点实测无横向溢出。

## 3. 架构

```
apps/web (React 18 + TS + Vite, 5274)
   │  /api 代理
   ▼
apps/server (FastAPI, 8720)
   ├─ core/     provider(mock|zhipu|dashscope|openai|local) · 工具注册表 · SSE · 安全中间件
   ├─ rag/      中文 2-gram + FTS5(BM25) [+ 向量 RRF 融合] · 引用定位
   ├─ domain/   inventory(计量/分级) · recipes(五步 Agent) · plan(3 天配餐) · reconcile(对账) · stats(碳账) · report(周报)
   ├─ api/      capture / receipt / inventory / reconcile / recipes / cook / plan / preferences / stats / report
   └─ db/       SQLite（12 表 + 1 FTS5）：items · inventory · recipes · images · waste_log
                reconcile_applied · events · agent_runs · preferences · meal_plans
                chunks · chunk_vectors + chunks_fts
apps/server/mcp/server.py  stdio JSON-RPC 的 MCP 服务（search_recipes / get_shelf_life）
```

Agent 五步：`understand → plan → retrieve → compose → verify`，每步状态与耗时落 `agent_runs`，前端「查看推理过程」可回放。

## 4. 本地启动

前置：Python 3.12+（本地 3.14 验证）、Node 20+、pnpm。以下命令除注明外均在项目根执行。

```powershell
# 后端（首次需建虚拟环境并装依赖）
cd apps/server
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
# 需要逐字节复现生产环境时改用：pip install -r requirements.lock
Copy-Item .env.example .env      # 按需填 SHIGUANG_LLM_PROVIDER / SHIGUANG_LLM_API_KEY（占位值，不是真实 key）
python -m uvicorn app.main:app --port 8720

# 前端（从项目根另开一个终端）
cd apps/web
pnpm install
pnpm dev                          # http://localhost:5274
```

不配 key 也能跑：默认 `SHIGUANG_LLM_PROVIDER=mock`，识别与推荐返回内置回放数据，并在页面标注「演示数据」。

**演示数据**（让统计页有曲线）：

```powershell
cd apps/server
python scripts/seed_demo.py --reset
```

**测试**：

```powershell
cd apps/server
python -m pytest -q                # 151 项（110 业务 + 31 交付前审查 + 10 静态托管/口径回归）
```

**真实模型自测**（会调用一次视觉接口）：

```powershell
cd apps/server
python scripts/probe_vlm.py ..\..\samples\fridge-1.jpg
```

> `samples/` 为自摄演示素材，**不入库**（`.gitignore` 已排除）。新 clone 后该目录为空，`probe_vlm.py` 会提示先放照片；请使用自己拍摄的冰箱照片，不要使用含个人信息或他人隐私的图片。

## 5. 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `SHIGUANG_LLM_PROVIDER` | `mock` | `mock` / `zhipu` / `dashscope` / `openai` / `local` |
| `SHIGUANG_LLM_BASE_URL` | 按预设 | 留空走预设 |
| `SHIGUANG_LLM_API_KEY` | 空 | 也可用用户环境变量 `ZHIPU_API` 回退 |
| `SHIGUANG_LLM_MODEL` | 按预设 | 文本模型 |
| `SHIGUANG_VLM_MODEL` | 按预设 | 视觉模型 |
| `SHIGUANG_EMBEDDING_PROVIDER` | `none` | `none` / `api` / `local`（BGE-M3） |
| `SHIGUANG_DB_PATH` | `data/app.db` | SQLite 路径 |
| `SHIGUANG_UPLOAD_DIR` | `data/upload` | 上传图片目录；部署时指向 `shared/upload`，切软链不丢图 |
| `SHIGUANG_PORT` | `8720` | 服务端口 |
| `SHIGUANG_WEB_DIST` | `apps/web/dist` | 前端构建产物（存在则托管并接管 `/`） |
| `SHIGUANG_BASIC_AUTH` | 空 | `user:pass`，公网演示必填 |
| `SHIGUANG_RATE_LIMIT_PER_MIN` | `0` | 每 IP 每分钟请求数 |
| `SHIGUANG_SSL_VERIFY` | `os` | `os` 系统信任库 / `strict` certifi / `off` 仅本地开发（本机 TLS 代理会替换证书链） |

## 6. 目录

```
apps/server/app/{config.py, core/, db/, rag/, domain/, api/, data/}
apps/server/{scripts/, tests/, mcp/}
apps/web/src/{components/, features/, lib/, styles/}
docs/        设计与交付文档（01 选题 → 10 提示词记录）
PLAN.md      72 小时倒排与提交物清单
```

## 7. 数据口径

- 保质期为家庭冷藏常见值；碳因子对齐公开食物碳足迹资料（量级：牛 > 猪 > 禽 > 蛋 > 蔬果）
- 重量 `grams = qty × avg_grams`；碳 `carbon_kg = grams/1000 × 因子`；浪费率 `thrown/(thrown+saved)`
- 全部为**估算值**，不作为食品安全或营养建议；详细来源见 `docs/06-数据来源与合规.md`

## 8. 外部服务与出网

| 场景 | 是否出网 | 说明 |
|---|---|---|
| `SHIGUANG_LLM_PROVIDER=mock`（默认） | **否** | 全部走内置回放数据，可离线演示 |
| `zhipu` / `dashscope` / `openai` | **是** | 图片（base64）与文本会发送到对应模型服务商的 API |
| `local` | 本机 / 内网 | 请求发往 `SHIGUANG_LLM_BASE_URL` 指定的本机或内网端点 |
| 图片上传 | 否（模型调用除外） | 本地开发写 `apps/server/data/upload/`；线上写 `/opt/shiguang/shared/upload/`，均不入库 |

- 无账号体系、无手机号/邮箱采集、无第三方统计 SDK；图片不用于训练、不二次分发。
- API key 只从 `.env` 或用户环境变量读取，不入库、不写日志。
- 外部模型服务受各自服务条款约束，本项目不转售、不批量抓取。

## 9. 复用与素材声明

- 工程脚手架结构（FastAPI + SQLite + React/Vite + SSE 流式）复用自本人往期项目 `yizhi-chengke`；检索思路参考本人存量 RAG 项目与 `skills/ai-memory`。业务逻辑（临期分级、五步 Agent 自检、碳账口径、库存对账）为本项目新写。详见 `docs/07-AI协作与原创性说明.md` §6。
- 演示冰箱照片为参赛者自摄，`samples/` 不入库；仓库不包含任何用户照片或第三方图库素材。
- 自建数据表（`items.json` / `recipes.json`）以 CC BY 4.0 提供，出处见 `docs/06-数据来源与合规.md` §2–§3。

## 10. 许可证

MIT（见 `LICENSE`）；第三方依赖与数据许可清单见 `THIRD-PARTY-NOTICES.md`。
