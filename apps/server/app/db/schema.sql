-- 食光（剩食管家）数据模型 —— 契约 §5 + RAG 索引表（契约 §8）
-- 时间一律 ISO8601 带时区；日期比较只取 date 部分。

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- 食材库（参考数据，来自 app/data/items.json）
CREATE TABLE IF NOT EXISTS items (
    id                TEXT PRIMARY KEY,
    name              TEXT UNIQUE NOT NULL,
    category          TEXT,
    shelf_life_days   INTEGER,
    carbon_kg_per_kg  REAL,
    price_per_kg      REAL,
    avg_grams         REAL,
    storage_tip       TEXT,
    unit              TEXT
);

-- 库存
CREATE TABLE IF NOT EXISTS inventory (
    id          TEXT PRIMARY KEY,
    item_id     TEXT,
    name        TEXT NOT NULL,
    qty         REAL,
    unit        TEXT,
    grams       REAL,
    added_at    TEXT,
    expires_at  TEXT,
    status      TEXT,               -- active|consumed|discarded
    image_id    TEXT,
    confidence  REAL,
    note        TEXT
);
CREATE INDEX IF NOT EXISTS idx_inventory_status ON inventory(status);
CREATE INDEX IF NOT EXISTS idx_inventory_expires ON inventory(expires_at);

-- 菜谱（参考数据，来自 app/data/recipes.json）
CREATE TABLE IF NOT EXISTS recipes (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    ingredients TEXT,               -- JSON [{name,qty,unit,optional}]
    steps       TEXT,               -- JSON [str]
    minutes     INTEGER,
    servings    INTEGER,
    tags        TEXT,
    difficulty  TEXT
);

-- 图片（识别痕迹，原图路径 + 识别结果 JSON）
CREATE TABLE IF NOT EXISTS images (
    id          TEXT PRIMARY KEY,
    path        TEXT,
    created_at  TEXT,
    recognized  TEXT
);

-- 浪费日志
CREATE TABLE IF NOT EXISTS waste_log (
    id            TEXT PRIMARY KEY,
    inventory_id  TEXT,
    name          TEXT,
    grams         REAL,
    reason        TEXT,
    carbon_kg     REAL,
    created_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_waste_created ON waste_log(created_at);

-- 业务事件（kind=consume 记「省下的食物」，用于统计口径）
CREATE TABLE IF NOT EXISTS events (
    id          TEXT PRIMARY KEY,
    kind        TEXT,
    payload     TEXT,
    created_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_kind ON events(kind, created_at);

-- Agent 运行轨迹（contract §6.7）
CREATE TABLE IF NOT EXISTS agent_runs (
    id          TEXT PRIMARY KEY,
    kind        TEXT,
    state       TEXT,
    steps       TEXT,
    created_at  TEXT
);

-- 用户偏好（契约 §6.10）：avoid 硬约束，其余软约束；source=dialog|manual
CREATE TABLE IF NOT EXISTS preferences (
    id          TEXT PRIMARY KEY,
    text        TEXT NOT NULL,
    kind        TEXT,               -- avoid|like|time|portion|health
    source      TEXT,               -- dialog|manual
    confidence  REAL,
    user_id     TEXT,
    created_at  TEXT,
    updated_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_preferences_kind ON preferences(kind);

-- 饮食计划存档（契约 §6.9 / §6.10）：revise 要读回原计划
CREATE TABLE IF NOT EXISTS meal_plans (
    id          TEXT PRIMARY KEY,
    payload     TEXT,               -- JSON：days/shopping/coverage/warnings/params
    created_at  TEXT,
    updated_at  TEXT
);

-- RAG 语料块（chunk）
CREATE TABLE IF NOT EXISTS chunks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source      TEXT NOT NULL,      -- recipe:<id> / tip:<n> / pref:<id>
    locator     TEXT NOT NULL,      -- 步骤 1-3 / 段落 2
    title       TEXT,
    body        TEXT,
    tokens      TEXT,               -- 2-gram 切分结果（空格分隔）
    created_at  TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_chunks_source_locator ON chunks(source, locator);

-- FTS5 全文索引（unicode61 + 应用层 2-gram 写入 tokens 列）
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    title,
    tokens,
    body,
    source UNINDEXED,
    locator UNINDEXED,
    tokenize = 'unicode61'
);

-- 向量缓存（可选向量召回，source=provider/model）
CREATE TABLE IF NOT EXISTS chunk_vectors (
    chunk_id    INTEGER PRIMARY KEY,
    model       TEXT,
    dim         INTEGER,
    vec         TEXT,               -- JSON float 数组
    created_at  TEXT
);
