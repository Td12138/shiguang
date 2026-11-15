# 第三方依赖与许可

本项目以 MIT 许可发布（见 `LICENSE`）。下列依赖均为宽松许可，未包含 GPL/AGPL 代码。

## 后端（apps/server）

| 依赖 | 用途 | 许可证 |
|---|---|---|
| FastAPI | Web 框架 | MIT |
| Uvicorn | ASGI 服务器 | BSD-3-Clause |
| httpx | HTTP 客户端 | BSD-3-Clause |
| Pydantic | 数据校验 | MIT |
| python-multipart | 文件上传解析 | Apache-2.0 |
| pytest / pytest-asyncio | 测试（仅开发） | MIT |

SQLite 为标准库 `sqlite3`（公共领域）；FTS5 为 SQLite 内置扩展。

## 前端（apps/web）

| 依赖 | 用途 | 许可证 |
|---|---|---|
| React / React DOM | UI 框架 | MIT |
| react-router-dom | 路由 | MIT |
| Vite | 构建工具 | MIT |
| TypeScript | 类型系统 | Apache-2.0 |
| @vitejs/plugin-react | Vite 插件 | MIT |

未引入 UI 组件库与图表库：设计系统为 CSS 变量 + CSS Modules，图表为手写 SVG。

## 数据

- 食材保质期、碳排因子、价格：参考公开食物碳足迹与食品保存资料整理，口径与误差见 `docs/06-数据来源与合规.md`
- 演示用冰箱照片：由参赛者自摄，不含第三方素材（`samples/` 不入库）
- 测试阶段使用的公开图片仅用于本地识别验证，不进入仓库与提交材料

## 字体

界面使用系统字体栈（不打包字体文件），无额外许可要求。
