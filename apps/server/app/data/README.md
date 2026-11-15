# app/data —— 种子数据说明

本目录是「食光」的**唯一数据来源**，服务端启动时由 `app/db` 灌入 SQLite（`apps/server/data/app.db`，不入库）。
所有数字都为演示与教学用途整理，**不是实验室检测值**，页面上必须保留「估算」字样。

## 文件清单

| 文件 | 内容 | 条数 | 被谁用 |
|---|---|---|---|
| `items.json` | 食材主数据（保质期 / 碳因子 / 价格 / 单件克重 / 保存建议） | 60 | `inventory`、`stats`、`capture` 匹配、`get_shelf_life` 工具 |
| `recipes.json` | 家常菜谱（食材、步骤、时长、标签） | 30 | `recipes`、RAG 语料、`find_recipes` 工具 |
| `tips.md` | 保存技巧，一节一条 | 20 | RAG 语料，`source` = `tip:<序号>` |
| `fixtures/recognize_fridge.json` | 模拟 VLM 识别输出，8 项 | 8 | `mock` provider 的 `chat_vision` |
| `fixtures/suggest.json` | 模拟菜谱推荐输出，3 条 | 3 | `mock` provider 的 `chat_json` |

格式与 `docs/03-定稿与契约.md` §5 字段一一对应；`recipes.ingredients/steps` 在文件里是真正的数组，落库时由 db 层 `json.dumps` 成 TEXT。

## 数据口径

| 字段 | 口径 |
|---|---|
| `shelf_life_days` | 家庭冰箱**冷藏 4℃**下的可食天数；标「冷冻」的条目（冷冻虾仁、冷冻牛肉卷、腐竹、面粉、生抽等）按 -18℃ 或常温干燥计 |
| `carbon_kg_per_kg` | 每公斤食材的**全生命周期碳排放当量**（kg CO₂e/kg，生产+加工+运输+零售，不含家庭烹饪与废弃处理） |
| `price_per_kg` | 2026 年国内一二线城市超市与菜场的常见零售价，取区间中值，单位元 |
| `avg_grams` | 一「单位」（个/颗/把/盒/袋/瓶/碗…）的可食部分平均克数，用于 `grams = qty × avg_grams` |
| `unit` | 购买时最自然的计量单位，和 `avg_grams` 绑定；菜谱里允许换成克/毫升 |
| 菜谱 `minutes` | 从洗菜到出锅的总时长，不含腌制等待之外的静置 |

## 数值分档（便于自查，不是精确值）

碳因子按公开食物碳足迹研究的量级分档，肉类比蔬菜高一到两个数量级，这是本项目的核心叙事：

| 档位 | 代表食材 | 取值 |
|---|---|---|
| 牛肉 | 牛腩、牛肉末、冷冻牛肉卷 | 60 |
| 奶酪 | 奶酪 | 21.2 |
| 虾 / 黄油 | 冷冻虾仁、黄油 | 12 |
| 猪肉 / 家禽 / 蛋 | 五花肉、鸡胸肉、鸡蛋 | 7.2 / 6.1 / 4.7 |
| 水产 / 乳 / 豆制品 | 三文鱼、牛奶、豆腐 | 5.1 / 3.2 / 3.0 |
| 主食 | 米饭、馒头、面条、面包 | 1.5–2.0 |
| 设施蔬菜 | 番茄、青椒、金针菇 | 0.9–1.4 |
| 露地蔬菜 / 水果 | 叶菜、根茎、苹果、橙子 | 0.4–0.8 |

## 哪些有依据、哪些是估算

| 有公开资料支撑 | 本项目估算 |
|---|---|
| 碳因子的**相对量级**（牛肉 ≫ 奶酪 > 猪禽蛋 > 蔬果），来自 Poore & Nemecek (2018) 及 Our World in Data 食物碳足迹汇总 | 具体小数（如 0.45、1.4）：按品类平均值就近取整，未逐项做 LCA |
| 冷藏/冷冻保质期的**基本规律**（叶菜 3–5 天、鸡蛋 30 天、冷冻肉 90 天），来自常见食品安全与冷藏建议 | 精确到「天」的单一数字：同一食材随产地、初始新鲜度、冰箱实际温度浮动 ±30% |
| 单件克重（一个鸡蛋 55 g、一颗大白菜 1.5 kg 等）为常见规格 | 把/颗类食材的克重：按市场常见一袋/一把估 |
| 零售价量级 | 价格随时节与城市波动，仅用于演示「省了多少钱」，不可作为报价 |

## 更新方式

1. 直接改本目录的 JSON / Markdown（字段名不得改，`id` 不得复用）。
2. 重建种子库：删掉 `apps/server/data/app.db` 后重启服务，或调 `init_db(force=True)`。种子只在库为空时灌入，改完文件必须重建才生效。
3. 自查（在 `apps/server` 下执行）：

```powershell
& E:\code\py_venv\.venv\Scripts\python.exe -c "import json,pathlib;d=pathlib.Path('app/data');i=json.loads((d/'items.json').read_text(encoding='utf-8'));r=json.loads((d/'recipes.json').read_text(encoding='utf-8'));n={x['name'] for x in i};print(len(i),len(n),len(r));print([(x['id'],g['name']) for x in r for g in x['ingredients'] if g['name'] not in n and not g.get('optional')])"
```

约定：

- `items.name` 唯一，且菜谱食材名必须**逐字**匹配；非常备调味料（盐、糖、淀粉、香油、料酒、醋、胡椒、豆瓣酱等）一律 `optional: true`。
- `items.id` 用英文小写下划线，供 `item_id` 引用；菜谱 `id` 用 `r_001` 递增，一经引用不得改号（`citations` 里是 `recipe:r_001`）。
- `tips.md` 每条以 `## ` 开头、正文 60–120 字，切分后一段就是一个 chunk。

## fixtures 说明

- `recognize_fridge.json` 只给 **VLM 原始输出**（name/qty/unit/confidence）。`item_id`、`shelf_life_days`、`expires_at`、`matched` 由服务端按 `items.json` 补算；`warnings` 也由服务端生成，规则：置信度 < 0.7 记一条、名称不在食材库记一条（此文件故意各留了一项：酸奶 0.55、秋葵 0.81，用于演示黄标与人工校对）。
- `suggest.json` 的 3 条 `recipe_id` 都是 `recipes.json` 里真实存在的条目，`citations` 指向真实 `recipe:` 与 `tip:` 源；`run_id` 由服务端在写入 `agent_runs` 后拼接，不放在 fixture 里。
- mock 模式下若 fixtures 缺失，服务端应回落到内置最小样例（见契约 §7），不要让演示链路断在数据上。
