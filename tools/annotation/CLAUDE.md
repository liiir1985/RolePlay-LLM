# Annotation Tool

## 架构

FastAPI + SQLite 后端，React + TypeScript + Vite 前端。

### 后端 (`backend/`)

- `main.py` — FastAPI app，CORS 中间件，挂载所有 router 到 `/api/` 前缀
- `database.py` — SQLite 连接工厂 (`get_conn()`)，`init_db()` 建表
- `routers/` — records, schemas, queues, datasets, cleaning

### 前端 (`frontend/`)

- Vite dev server 端口 5173，proxy `/api` → `http://localhost:8000`
- `src/App.tsx` — BrowserRouter + 侧边栏导航 + Routes
- `src/api.ts` — 集中 API 客户端，所有请求走 `req<T>(path, options)`
- `src/pages/` — 每个功能一个页面组件
- `src/components/JsonViewer.tsx` — 可折叠 JSON 树组件（基于 react-json-view-lite），递归解析嵌套 JSON 字符串，`\n` 以换行显示
- `src/index.css` — 全局样式（Catppuccin 风格暗色侧边栏 + 亮色内容区）

## 数据库 Schema

```sql
records (id TEXT PK, type, name, timestamp, depth, input TEXT[JSON], output TEXT[JSON], metadata TEXT[JSON], created_at)
annotation_schemas (id INTEGER PK, name UNIQUE, created_at)
schema_fields (id, schema_id FK, name, label, type, options, order_idx)
queues (id, name UNIQUE, schema_id FK, created_at)
queue_items (id, queue_id FK CASCADE, record_id FK, status DEFAULT 'pending', created_at, UNIQUE(queue_id,record_id))
annotations (id, queue_item_id FK UNIQUE CASCADE, "values" TEXT[JSON], updated_at)
datasets (id, name UNIQUE, created_at)
dataset_items (id, dataset_id FK CASCADE, record_id FK, source, queue_item_id FK, UNIQUE(dataset_id,record_id))
```

## Record 数据格式

每条 record 代表一次 AI API 调用（来自 LiteLLM/Langfuse 等）：

- `id`: 唯一标识
- `timestamp`: 单一时间戳字段（原始数据中的 `timestamp`，fallback 到 `startTime`）
- `input`: JSON 字符串，核心字段 `{"messages": [...]}`
  - messages 是 ChatML 格式数组，每条有 `role` (system/user/assistant/tool) 和 `content`
  - content 可能是 string 或 array（Anthropic 格式：`[{type:"text", text:"..."}, {type:"tool_use", id, name, input}, ...]`）
- `output`: JSON 字符串，`{content, role:"assistant", tool_calls, ...}`
  - tool_calls 格式（OpenAI）：`[{id, type:"function", function:{name, arguments(string)}}]`

## 会话链关系

同一会话中，记录 A 的 output 会出现在后续记录 B 的 input.messages 的某个 assistant 轮次中（可能被 strip/截断但不会被改写）。

## API 端点

### Records `/api/records`
- `POST /import` — 导入 JSONL 文件
- `GET /` — 列表（分页 + search + start_time/end_time 时间段筛选），返回 `{id, timestamp, input_preview, output_preview}`

### Schemas `/api/schemas`
- CRUD: `GET /`, `POST /`, `GET /{id}`, `PUT /{id}`, `DELETE /{id}`

### Queues `/api/queues`
- `GET /`, `POST /`, `GET /{id}`, `DELETE /{id}`
- `POST /{id}/items` — 添加指定 record_ids
- `POST /{id}/items/all` — 按筛选条件批量添加全部（body: search, start_time, end_time）
- `GET /{id}/item-ids` — 返回所有 item id 数组（轻量，用于前后导航）
- `GET /{id}/items` — 分页列表（status/start_time/end_time 筛选），返回 `{id, record_id, status, timestamp, input_preview, output_preview}`
- `GET /{id}/items/{iid}` — 单条详情（含完整 input/output/metadata/annotation）
- `POST /{id}/items/{iid}/annotate` — 保存标注

### Datasets `/api/datasets`
- `GET /`, `POST /`, `DELETE /{id}`
- `POST /{id}/items/raw` — 添加原始记录
- `POST /{id}/items/annotated` — 添加已标注记录
- `GET /{id}/items` — 分页列表（source/start_time/end_time/ann_filter 筛选），返回含 annotations 字段
- `DELETE /{id}/items/{iid}`
- `GET /{id}/export` — 导出 JSONL

### Cleaning `/api/cleaning`
- `POST /merge-preview` — 预览可合并的会话链
- `POST /merge-execute` — 执行合并

## 页面功能

| 路由 | 页面 | 功能 |
|------|------|------|
| `/records` | Records | 导入 JSONL、时间段筛选（datetime-local）、显示 ID/timestamp/input前100字/output前100字 |
| `/schemas` | Schemas | 创建/编辑评估模板（modal 不响应点击外部关闭，防止拖拽丢失） |
| `/queues` | Queues | 创建评估队列（选择 schema） |
| `/queues/:id` | QueueDetail | 队列详情、添加数据（支持日历筛选+全选当前页+选择全部含其他页+分页）、列表显示统一字段 |
| `/queues/:id/items/:iid` | QueueItemDetail | 标注页面：左侧 JsonViewer 展示 input/output，右侧评估字段，上一条/下一条/保存并下一条导航 |
| `/datasets` | Datasets | 创建数据集、添加原始/已标注数据（统一字段+分页+筛选）、annotation 字段筛选、导出 JSONL |
| `/cleaning` | Cleaning | 数据清洗（合并会话记录等） |

## 关键设计决策

- 所有 modal 弹窗不使用 click-outside-to-close（防止拖拽文本到窗口外导致意外关闭）
- 列表统一显示字段：ID、timestamp、input 前100字、output 前100字
- 后端 `_preview()` 函数截取前100字符作为预览
- 评估页面通过 `/item-ids` 接口获取全量 id 列表实现前后导航（避免 limit 200 限制）
- 时间筛选使用 `datetime-local` 原生组件，后端按 `timestamp` 字段比较

## 开发命令

```bash
# 后端
cd tools/annotation/backend && uvicorn main:app --reload

# 前端
cd tools/annotation/frontend && npm run dev
```

## 代码风格

- 后端：FastAPI router 模式，Pydantic BaseModel 做请求体，`with get_conn() as conn` 管理事务
- 前端：函数组件 + hooks，内联样式为主，modal overlay 模式做弹窗（不 click-outside-close），中文 UI
- 前端依赖：react, react-router-dom, react-json-view-lite
