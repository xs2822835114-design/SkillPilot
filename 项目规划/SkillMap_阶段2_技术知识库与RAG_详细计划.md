# SkillMap 阶段 2 详细实施计划 — 技术知识库与 RAG

> 对应：《SkillMap_个人技术栈成长智能体_项目计划书》阶段 2
> 版本：V1.0
> 风格：模块解耦 + 契约先行 + 并行开发（与阶段 1 详细计划保持同一套行文规范）

---

## 1. 阶段定位与目标

**一句话目标**：在阶段 1 的管道之上，建立「可更新的技术知识库 + 向量检索 + 带证据的问答」，让 Agent 能基于最新、可追溯的技术资料作答，并为后续 Gap/Planner 等业务 Agent 提供 role/skill 检索能力。

**为什么必须先做阶段 2**：计划书里 5 个业务 Agent 几乎都依赖"技术资料"——Gap 需要岗位要求/技能定义做缺口分析，Planner 需要推荐学习资源，问答链需要证据来源。阶段 2 先把「入库→切块→向量化→检索→带来源问答」这条知识管道打通并锁定契约，后续阶段只需"往检索里加 filter"。

**本阶段核心目标拆解**

| # | 目标 | 验收可测性 |
| --- | --- | --- |
| G1 | 知识库表结构与 pgvector 就绪 | `init_db` 可重复执行且建出 rag 表与向量索引 |
| G2 | 文档入库可用 | `POST /rag/ingest` 落库并返回 `doc_id` |
| G3 | 检索可用 | `POST /rag/search` 返回 Top-K，含 `source/title/url/chunk_id` |
| G4 | 检索可过滤 | 支持按技术类别等 metadata 过滤 |
| G5 | 问答带证据 | RAG 问答回复附 evidence，含来源信息 |
| G6 | 契约稳定 + 兜底 | 有测试守护；Embedding/LLM 不可用时仍返回标准结构 |

---

## 2. 范围边界

### 2.1 本阶段做什么（In Scope）

- pgvector 扩展启用 + `rag_documents` / `rag_chunks` 表与索引（纳入 `scripts/init_db.py`）
- 文档加载 Pipeline（Loader）：本地文本/ Markdown、URL 抓取文本（先做文本类，PDF 等后续按需）
- 切块（Splitter）：按 token/字符 + 重叠切块，产出 chunk + metadata
- Embedding（Qwen/DashScope 兼容端点）：`app/rag/embeddings.py` 抽象客户端
- VectorStore（直接走 psycopg SQL，风格对齐阶段 1 的 `thread_store`）
- Retriever：Top-K 余弦检索 + metadata filter
- RAG 问答链：检索 → 组 prompt → LLM → 答案 + evidence
- 三个接口：`POST /rag/ingest`、`POST /rag/search`、`POST /rag/query`
- 第一批 30~50 份高质量技术资料（.md/.txt/URL）
- 用于后续 Gap 的 `category` / `skill_tags` / `role_target` 检索维度预留
- 阶段 2 契约文档 + 集成测试

### 2.2 本阶段明确不做（Out of Scope）

| 不做 | 原因 | 何时做 |
| --- | --- | --- |
| 各业务 Agent 接入检索 | 先交付稳定检索接口，接入随阶段 3+ 业务 Agent | 阶段 3~6 |
| PDF/Word 复杂解析、OCR | 首批资料用文本/Markdown，尽量降风险 | 按需后置 |
| 流式 SSE 问答 | 阶段 1 既定非流式，SSE 保留事件类型预留 | 阶段 8（或本阶段按需试点） |
| Re-ranking / 多路召回 | 阶段 2 先用朴素 Top-K 余弦 | 后续阶段 |
| 前端检索/知识库管理页 | 后端契约先行 | 阶段 8 |

> 边界原则（对齐计划书 1.1）：**MVP 先做单路检索**，再逐步加工程化；不为"以后可能用到"提前上重构能力。

---

## 3. 技术选型与工程结构

### 3.1 技术栈（在阶段 1 基础上新增）

| 项 | 选型 | 说明 |
| --- | --- | --- |
| 向量扩展 | PostgreSQL `pgvector`（HNSW，vector_cosine_ops） | 复用现有 PostgreSQL 16，不引入新数据库 |
| Embedding | DashScope / Qwen OpenAI 兼容端点 | `compatible-mode/v1/embeddings`，模型名与维度可配 |
| 切块 | `langchain-text-splitters`（RenarationSplitter 起步） | 复用现有 langchain 生态 |
| URL 抓取 | `requests` | 轻量、通用 | 
| pgvector 适配 | `pgvector` Python 包（Vector 类型） | psycopg3 无法直接绑定 list→vector，用它做类型适配 |

> 新增依赖（写入 `pyproject.toml` `[project.dependencies]`）：
> `langchain-text-splitters>=0.3`、`pgvector>=0.3.0`、`requests>=2.31`

### 3.2 工程结构（新增/修改点，模块即边界）

```
app/                      # 存量不动，仅新增 + 少量接线
├── config.py             # 修改：新增 EMBEDDING_* / RAG_* / DB_VECTOR 配置项
├── api/routes/
│   ├── rag.py            # 新增：POST /api/v1/rag/ingest|search|query（仅 HTTP 入出）
│   └── __init__.py       # 修改：注册 rag_bp
├── rag/                  # 新增：【知识层】RAG 业务管道（不感知 HTTP）
│   ├── __init__.py
│   ├── schemas.py        # RAG Pydantic 契约（ingest/search/query进与出）
│   ├── loader.py         # Loader：file/markdown/URL → text(+metadata)
│   ├── splitter.py       # Splitter：text → list[chunk]（保留来源 metadata）
│   ├── embeddings.py     # EmbeddingClient 抽象：Qwen 兼容端点 / 确定性兜底
│   ├── vectorstore.py    # pgvector 读写 + HNSW 索引 + 向量查询（psycopg 直连）
│   ├── retriever.py      # Top-K + metadata filter → Evidence
│   └── qa_chain.py       # 检索→组prompt→LLM→答案+evidence（容错）
└── persistence/
    └── ...               # 复用 db.connect；不新增持久化层
scripts/
└── init_db.py            # 修改：启用 vector 扩展 + 建 rag 表/索引（幂等）
tests/
└── test_rag_integration.py  # 新增：TC-R1~TC-R10
```

分层依赖（延续单向规则）：

```
API 层 api/routes/rag.py
   │  只调
   ▼
知识层 app/rag/（vectorstore → retriever → qa_chain；loader/splitter/embeddings 供 ingest 用）
   │  只调
   ▼
持久化 app/persistence/db.py（psycopg）
```

**接线点（改动最小化）**
- `app/__init__.py` 的 `create_app`：注册 `rag_bp`。
- `app/config.py`：加 Embedding/RAG 配置。
- `scripts/init_db.py`：追加 `CREATE EXTENSION IF NOT EXISTS vector` 与两张 rag 表 + 索引。
- `docs/api_v1.md`：补 RAG 三接口（或新开 `docs/rag_v1.md`，建议并入 api_v1.md 保持单文档）。

---

## 4. 模块解耦与分工

### 4.1 各模块职责、输入、输出、不负责什么

| 模块 | 职责 | 主要输入 | 主要输出 | 不负责什么 |
| --- | --- | --- | --- | --- |
| API 层（`routes/rag.py`） | 收 HTTP、校验、调知识层、包统一响应 | HTTP JSON | 统一 response | 不做切块/向量/检索细节 |
| 编排/问答（`qa_chain.py`） | 检索→组装 prompt→LLM→答案+evidence | query + filter + top_k | QAAnswer(含evidence) | 不写 HTTP、不持久化 |
| 检索（`retriever.py`） | Top-K + filter | query_embedding + filter | list[Evidence] | 不调 LLM、不切块 |
| 向量存取（`vectorstore.py`） | 落库/建索引/向量查询 | config + vector + metadata | 查询/写入结果 | 不做业务判断 |
| 入库管道（loader/splitter/embedding） | 抓取→切块→向量化 | 文档/URL + 配置 | chunk + embedding | 不检索、不问答 |

### 4.2 团队分工（阶段 2 建议 2~3 角色，可并行）

| 角色 | 负责模块 | 主要交付物 | 依赖 | 是否可并行 |
| --- | --- | --- | --- | --- |
| 平台/后端 | config、`routes/rag.py`、`vectorstore.py`、`init_db` 改造、测试基线 | 建表+索引、三接口骨架、统一响应 | 无（先定契约后并行） | 是 |
| 知识管线 | loader、splitter、embeddings、retriever、qa_chain | 入库/检索/问答走通 | 依赖契约 + vectorstore 就绪 | 契约后并行 |
| 资料/测试 | 30~50 份资料整理、`test_rag_integration.py` | 首批语料、TC-R1~R10 | 两端交付后联调 | 可先写契约断言与语料 |

> 并行关键仍是**先冻结契约**（第 5、6 节 schema），再各自开发。

---

## 5. 输入 / 输出接口契约（RAG）

通用约定沿用阶段 1：成功 `{"code":0,"message":"ok","data":...}`；错误带 `trace_id`；字段 snake_case。错误码沿用阶段 1 子集（40001/42200/40400/50000，可新增 `50010` Embedding 失败、`50011` 检索失败，见第 7 节）。

### 5.1 POST /api/v1/rag/ingest —— 入库

```jsonc
// 请求
{
  "source": "https://example.com/ai-agent-guide.md",  // 或本地文件路径/内容
  "source_type": "url",                                // url | file | text
  "content": null,                                     // 当 source_type=text 时提供
  "category": "ai",                                    // 技术类别，参与过滤
  "title": "AI Agent 入门指南",
  "lang": "zh",
  "skill_tags": ["agent", "rag"],
  "role_target": "ai_application_engineer"             // 预留：供后续 Gap 检索
}
```

```jsonc
// 响应 200 data
{
  "doc_id": "DOC_8f3a2b",
  "num_chunks": 24,
  "status": "ok"
}
```

### 5.2 POST /api/v1/rag/search —— 检索

```jsonc
{
  "query": "什么是 RAG？",
  "top_k": 5,
  "filter": { "category": "ai", "source_type": null, "doc_id": null, "skill_tags": null }
}
```

```jsonc
{
  "results": [
    {
      "chunk_id": "CHK_xx",
      "doc_id": "DOC_8f3a2b",
      "title": "AI Agent 入门指南",
      "source": "https://example.com/ai-agent-guide.md",
      "url": "https://example.com/ai-agent-guide.md",
      "category": "ai",
      "content": "RAG 是检索增强生成（Retrieval-Augmented Generation）…",
      "score": 0.914
    }
  ]
}
```

### 5.3 POST /api/v1/rag/query —— 问答（RAG + LLM）

```jsonc
{
  "query": "帮我解释 RAG，并给出官方来源",
  "top_k": 4,
  "filter": { "category": "ai" }
}
```

```jsonc
{
  "answer": "RAG 是指…（基于以下资料）",
  "evidence": [
    {
      "chunk_id": "CHK_xx",
      "title": "AI Agent 入门指南",
      "source": "https://example.com/ai-agent-guide.md",
      "url": "https://example.com/ai-agent-guide.md",
      "category": "ai",
      "content_preview": "RAG 是检索增强生成…"
    }
  ],
  "qa_model": "deepseek-v4-flash",
  "top_k_used": 4
}
```

### 5.4 字段与校验规则

| 接口 | 字段 | 约束 |
| --- | --- | --- |
| ingest | `source`/`content` | 至少提供一个；`source` 为 url 时需 http(s)；文本长度上限（如 100_000 字符） |
| ingest | `source_type` | 枚举 `url/file/text` |
| search | `query` | 1~8000，去空白 |
| search | `top_k` | 1~20，默认 5 |
| 全部 | `category`/`title`/`lang`/`skill_tags`/`role_target` | 长度/格式校验，非法即 422 |

### 5.5 配置输入（环境变量，`app/config.py` 新增）

| 环境变量 | 必填 | 说明 | 示例 |
| --- | --- | --- | --- |
| `EMBEDDING_PROVIDER` | 否 | `openai`(DashScope兼容) ｜ `off`(确定性兜底) | `openai` |
| `EMBEDDING_BASE_URL` | 否 | 兼容端点 | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| `EMBEDDING_API_KEY` | 否 | 密钥（放 `.env`，不入库/日志） | `<你的key>` |
| `EMBEDDING_MODEL` | 否 | 模型名（兼容模式下别名需实测） | `qwen3.7-text-embedding` |
| `EMBEDDING_DIM` | 否 | 向量维度，**必须与模型输出一致**并匹配建表维度 | `1024` |
| `RAG_TOP_K_DEFAULT` | 否 | 默认检索条数 | `5` |
| `RAG_CHUNK_SIZE` / `RAG_CHUNK_OVERLAP` | 否 | 切块大小/重叠 | `800` / `100` |

> ⚠️ 模型名与维度：OpenAI 兼容模式下，`qwen3.7-text-embedding` 的真实别名需要先用一条 embedding 请求实战确认（若该别名不被兼容端点识别，回退用 `text-embedding-v4` 或 `text-embedding-v3`），并据此设置 `EMBEDDING_DIM`；建表 `vector(N)` 的 N 必须与之一致。

---

## 6. 数据契约与存储

### 6.1 document / chunk metadata（契约字段）

- **document 元数据**：`doc_id`、`title`、`source`、`source_type(url|file|text)`、`category`、`lang`、`role_target`、`skill_tags[]`、`meta(jsonb)`、`created_at`、`updated_at`
- **chunk 元数据**：`chunk_id`、`doc_id`、`chunk_index`、`content`、`token_count`、`embedding(vector)`、`created_at`

### 6.2 建表 SQL（纳入 `scripts/init_db.py`，幂等）

```sql
-- 启用向量扩展（前提：服务器已装 pgvector；Linux 需 postgresql16-pgvector 包，macOS brew 装 pgvector）
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS rag_documents (
  doc_id      VARCHAR(64) PRIMARY KEY,
  title       VARCHAR(255),
  source      TEXT,
  source_type VARCHAR(32) DEFAULT 'text',
  category    VARCHAR(64),
  lang        VARCHAR(16) DEFAULT 'zh',
  role_target VARCHAR(64),
  skill_tags  TEXT[],
  meta        JSONB DEFAULT '{}',
  created_at  TIMESTAMPTZ DEFAULT now(),
  updated_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS rag_chunks (
  chunk_id    VARCHAR(64) PRIMARY KEY,
  doc_id      VARCHAR(64) NOT NULL REFERENCES rag_documents(doc_id) ON DELETE CASCADE,
  chunk_index INTEGER NOT NULL,
  content     TEXT NOT NULL,
  token_count INTEGER DEFAULT 0,
  embedding   vector(1024),              -- 维度须对齐 EMBEDDING_DIM
  created_at  TIMESTAMPTZ DEFAULT now()
);

-- 检索索引：HNSW + 余弦
CREATE INDEX IF NOT EXISTS idx_rag_chunks_embedding
  ON rag_chunks USING hnsw (embedding vector_cosine_ops);

-- 过滤索引
CREATE INDEX IF NOT EXISTS idx_rag_documents_category ON rag_documents(category);
CREATE INDEX IF NOT EXISTS idx_rag_chunks_doc ON rag_chunks(doc_id);
```

### 6.3 初始化时机（延续阶段 1 约定）

- `CREATE EXTENSION` 与建表/索引只在 `scripts/init_db.py`（启动/迁移期）执行一次，**禁止**在入库/检索的业务路径里重复 `CREATE`。

---

## 7. 功能清单

| # | 功能 | 关联目标 |
| --- | --- | --- |
| F1 | pgvector 扩展 + rag 两表 + HNSW 索引（init_db 幂等） | G1 |
| F2 | `POST /rag/ingest`：文本/Markdown/URL → 切块 → 向量化 → 落库 | G2 |
| F3 | 相同 `source` 重复入库幂等（先删后插/按 doc_id upsert） | G5 |
| F4 | `POST /rag/search`：Top-K 余弦检索 | G3 |
| F5 | metadata filter（category/skill_tags/doc_id/source_type/role_target） | G4 |
| F6 | `POST /rag/query`：RAG 问答 + evidence 来源 | G5 |
| F7 | Embedding/LLM 不可用或失败时确定性兜底（哈希向量 + 规则回答），结构不变 | G6 |
| F8 | `/health` 增加可选 `embedding` 连通性字段（有 key→ok/disabled） | G6 |
| F9 | `docs/api_v1.md` 补 RAG 三接口 | G5 |
| F10 | 首批 30~50 份技术资料入库 + Git 内维护语料清单 | G2/G4 |

---

## 8. 验收标准与测试用例

### 8.1 验收条件（全部满足即完成）

| 编号 | 验收项 | 验证方式 |
| --- | --- | --- |
| AC1 | 库表/Ustay 索引就绪 | `init_db` 可重复执行；`\dt rag_*` 存在；`\dx` 含 vector |
| AC2 | 入库可用 | ingest 后 `rag_chunks` 有记录，返回 `doc_id/num_chunks` |
| AC3 | 检索可用 | 给定 query 返回 Top-K，结果含 `chunk_id/doc_id/title/source/url` |
| AC4 | 过滤有效 | 加 `category` 过滤后只返回该类结果 |
| AC5 | 问答带证据 | `query` 返回 `answer` 且 `evidence` 每条含来源字段 |
| AC6 | 兜底稳定 | 无 key 或 Embedding 报错仍返回标准结构，不 500 裸抛 |
| AC7 | 契约有测试 | TC-R1~R10 全绿 |

### 8.2 集成测试用例（`tests/test_rag_integration.py`）

| 用例 | 输入 | 预期 |
| --- | --- | --- |
| TC-R1 空库检索 | 未入库时 search | 200，`results==[]` |
| TC-R2 单文档入库 | ingest 一段 text | `doc_id` 返回、`num_chunks>0` |
| TC-R3 重复入库幂等 | 同一 source 两次 ingest | 第二次不产生重复 chunk（替换式） |
| TC-R4 Top-K 检索 | query + top_k=3 | 返回 ≤3 条，含来源字段与 score |
| TC-R5 过滤生效 | filter.category='ai' | 结果 category 全为 'ai' |
| TC-R6 问答带证据 | rag/query | `answer` 非空，`evidence` 含 source/title/url/chunk_id |
| TC-R7 非法入参 | query 空 / top_k 越界 | 422 + code 42200 + trace_id |
| TC-R8 坏 JSON | 非 JSON body | 400 + code 40001 |
| TC-R9 Embedding 兜底 | 配置 off / 注入失败 | 仍返回标准结构（hash 向量 / 规则回复） |
| TC-R10 文档隔离 | filter.doc_id=X | 只返回 X 的 chunk |

> TC-R9 用 `EMBEDDING_PROVIDER=off` 或 mock Embedding 抛错来稳定复现，不与真实 API 耦合。

---

## 9. 任务拆解与并行分工

### 9.1 前置（契约对齐，先做）

- [ ] 敲定第 5、6 节 schema（ingest/search/query 入出 + document/chunk metadata）
- [ ] 确认 Embedding 模型实测别名与维度，回填 `EMBEDDING_MODEL` / `EMBEDDING_DIM`
- [ ] 确认服务器已装 pgvector（否则先装），打通 `CREATE EXTENSION vector`

### 9.2 平台/后端（与知识管线并行）

1. `pyproject.toml` 加 `langchain-text-splitters` / `pgvector` / `requests`
2. `config.py` 新增 `EMBEDDING_*`/`RAG_*`
3. `init_db.py`：`CREATE EXTENSION` + rag 建表/索引
4. `routes/rag.py` 三接口骨架 + `register` rag_bp
5. 复用 `errors.py` 统一响应；新增 `50010/50011` 错误码
6. 测试基线：RAG 契约断言工具

### 9.3 知识管线（契约后并行）

1. `vectorstore.py`：psycopg 直连 + pgvector Vector 适配 + 写入/查询/HNSW
2. `embeddings.py`：Qwen 兼容端点 + 确定性兜底
3. `splitter.py` + `loader.py`：切块与抓取
4. `retriever.py`：Top-K + filter
5. `qa_chain.py`：RAG 问答（复用阶段 1 的 LLM 容错思路）
6. 与后端联调三接口

### 9.4 资料/测试

1. 整理 30~50 份首批资料（.md/.txt/URL，标注 category/skill_tags）
2. 实现 TC-R1~R10
3. 输出验收核对清单（AC1~AC7）

### 9.5 里程碑

| 里程碑 | 内容 | 完成标志 |
| --- | --- | --- |
| M1 | 契约冻结 + Embedding 实测 | schema 签署、模型别名/维度确认 |
| M2 | 库表/索引就绪 | `\dx` 含 vector、rag 表存在 |
| M3 | 入库走通 | ingest 落库返回 doc_id |
| M4 | 检索走通 | search Top-K + filter 生效 |
| M5 | 问答带证据 | rag/query 返回 answer + evidence |
| M6 | 测试与文档 | TC-R1~R10 全绿 + api_v1.md 更新 |

---

## 10. 风险与注意事项

| 风险 | 表现 | 应对 |
| --- | --- | --- |
| pgvector 未安装 | `CREATE EXTENSION vector` 报错 | 服务器：`dnf install postgresql16-pgvector`；macOS：`brew install pgvector`；容器则镜像内装 |
| 维度不匹配 | 插入 vector 报错 | 先实测模型输出维度，统一 `EMBEDDING_DIM` 与建表 `vector(N)` |
| Embedding 别名不被兼容端点识别 | 首次请求 4xx | 准备回退模型 `text-embedding-v4/‌v3`；在 M1 先探活 |
| 密钥泄露/进日志 | 配置入库或日志打印 | key 只放 `.env`（已 gitignore）；日志/错误不打印完整 key、完整 embedding |
| 切块不当 | 检索碎片化/上下文截断 | 先 RecursiveCharacter Splitter，按类别调 chunk_size/overlap |
| 检索质量差 | Top-K 相关性一般 | 阶段 2 用余弦+filter，后续再加 re-rank/BM25 融合 | 
| 入库重复 | 同文档多次导入导致噪音 | 以 source 做幂等（先删旧 doc 再插） |
| URL 抓取失败/受限 | ingest 报错 | loader 失败记日志并返回明确 4xx/5xx，不静默 |
| 契约随意改 | 前后端/测试返工 | 阶段内改动需评审并同步测试断言 |

---

## 11. 交付物清单（阶段 2）

- [ ] pgvector 扩展 + `rag_documents`/`rag_chunks` 表与 HNSW 索引（`init_db` 幂等）
- [ ] `app/rag/`：loader / splitter / embeddings / vectorstore / retriever / qa_chain
- [ ] `POST /api/v1/rag/ingest | search | query` 三接口
- [ ] metadata filter（category / skill_tags / doc_id / source_type / role_target）
- [ ] RAG 问答 evidence 结构 + 兜底
- [ ] `config.py` Embedding/RAG 配置 + `50010/50011` 错误码
- [ ] `docs/api_v1.md` 增补 RAG 契约
- [ ] 首批 30~50 份技术资料
- [ ] `tests/test_rag_integration.py`（TC-R1~R10）全绿
- [ ] 验收核对清单（AC1~AC7）