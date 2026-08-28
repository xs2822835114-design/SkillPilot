# SkillMap 阶段 3 详细实施计划 — 用户技术画像（Profile）

> 对应：《SkillMap_个人技术栈成长智能体_项目计划书》阶段 3"用户技术画像"
> 版本：V1.0
> 风格：模块解耦 + 契约先行 + 并行开发（与阶段 1、2 详细计划保持一致的行文规范）

---

## 1. 阶段定位与目标

**一句话目标**：把用户的技能栈从自然语言、项目经历、历史记录中**结构化**为可计算、可增量更新的能力画像（`SkillProfile`），并沉淀 `SkillsEvidence` 与 `UserPreference`，为阶段 4 的 Gap 分析提供确定性的"当前能力"输入。

**为什么必须先做阶段 3**：阶段 4 的角色 `GapAnalysisRequest` 需要 `current_profile_version`；阶段 5 规划需要"学了什么/会什么"。若没有一份**可由规则校验、可版本化、带证据**的画像，后续所有分析都会退化成对用户自由文本的反复解析。阶段 3 先把"自然语言 → 结构化技能画像"这条管道打通并锁定输出结构，后续 Gap/Planner 只消费 `SkillProfile` 快照，不再重复解析。

**本阶段核心目标拆解**

| # | 目标 | 验收可测性 |
| --- | --- | --- |
| G1 | 结构化技能画像 | 输入自然语言 → 返回结构化 `skills[]`（含 level/theory/practice/confidence） |
| G2 | 证据可追溯 | 每条技能关联 `evidence_id`（来源：自述/项目/会话） |
| G3 | 技能等级可计算 | `level` 由 theory_score/practice_score 经规则得出，非 LLM 随意给分 |
| G4 | 增量更新不覆盖 | 只更新 patch 中出现的技能，不影响无关技能，且保留/合并证据 |
| G5 | 项目与技能关联 | 登记项目可从简介提取技能并绑定 `projects.skills` |
| G6 | 契约稳定 + 兜底 | 有测试守护；LLM 提取失败时仍返回标准结构（空技能列表 + 兜底） |

---

## 2. 范围边界

### 2.1 本阶段做什么（In Scope）

- 建表：`skills`（技能字典）、`user_skills`（用户画像）、`projects`（项目）+ `user_preferences`（画像化偏好）
- `skills` 字典种子：由阶段 2 技能关系库（`SkillPilot_skill_relations.json`）+ 岗位能力库（`SkillPilot_role_competencies.json`）的技能名归一去重生成
- Profile 提取：`POST /api/v1/profile/extract`——自然语言/项目简介 → `SkillProfilePatch`
- Profile 登记/增量更新：`POST /api/v1/profile/upsert`
- Profile 查询：`GET /api/v1/profile/{user_id}`
- 项目登记与技能绑定：`POST /api/v1/profile/projects`
- `Skill Service`：技能字典检索、等级换算规则（theory/practice → level）、合并/增量策略
- 技能等级规则（rule engine）与 `SkillProfile.version`
- 契约文档 + 集成测试（TC-P1~P10）

### 2.2 本阶段明确不做（Out of Scope）

| 不做 | 原因 | 何时做 |
| --- | --- | --- |
| Gap 分析、学习计划 | 消费画像做差集/规划的 Agent | 阶段 4、5 |
| 完整三类长期记忆（Semantic/Episodic/Procedural namespaces、压缩、跨 thread） | 阶段 7 专门负责记忆抽象 | 阶段 7 |
| 代码仓库深度扫描、GitHub 深度集成 | 本阶段仅"项目简介→技能"，不读仓库代码 | 阶段 6/1.5 |
| 前端/雷达图/成长报告 | 本阶段只出后端契约 | 阶段 8 |
| JSON Schema / OpenAPI 生成 | 沿用阶段 1 统一响应 | 阶段 8（或按需） |

> 边界原则（对齐计划书 11、12 节）：本阶段把画像**存得下、提得出、更新得了**即可；**不做**记忆检索和复杂图编排，避免提前引入阶段 7 的能力。

---

## 3. 技术选型与工程结构

### 3.1 技术栈（在阶段 1、2 基础上，几乎无新增重量级依赖）

| 项 | 选型 | 说明 |
| --- | --- | --- |
| 存储 | PostgreSQL（复用阶段 1 `psycopg` 直连风格） | 不新增数据库 |
| 结构化输出 | Pydantic + LLM 可绑定工具返回 JSON | 延续阶段 1 `schemas.py` 风格 |
| 技能字典 | `skills` 表 + 启动种子 | 由阶段 2 两份 JSON 生成 |
| 等级规则 | 纯 Python 规则（非 LLM） | 保证 G3 可重复 |
| LLM 提取 | 复用阶段 1 `LLMClient`，仅解释/抽取 | 失败走规则兜底 |

> 本阶段不新增第三方依赖（可复用 langchain-openai / pydantic / psycopg）。若实操中发现结构化抽取不稳，可加 `instructor` 或 `langchain.output_parser.PydanticOutputParser`（列为可选，M1 决策）。

### 3.2 工程结构（新增/修改点，模块即边界）

```
app/
├── config.py                  # 修改：新增 PROFILE_* 配置（如默认等级换算参数）
├── api/routes/
│   ├── profile.py             # 新增：POST /api/v1/profile/{extract,upsert,projects}、GET /profile/{user_id}
│   └── __init__.py            # 修改：注册 profile_bp
├── profile/                   # 新增：【画像层】不感知 HTTP
│   ├── __init__.py
│   ├── schemas.py             # 契约：SkillProfilePatch / SkillProfile / SkillEvidence / UserPreference
│   ├── skill_service.py       # 技能字典检索、等级换算规则、合并/增量策略
│   ├── extractor.py           # LLM 抽取：content → SkillProfilePatch（结构化输出 + 兜底）
│   ├── store.py               # user_skills/projects/user_preferences 读写（psycopg 直连）
│   └── rule_engine.py         # theory/practice → level、confidence 合并等规则
└── persistence/
    └── ...                    # 复用 db.connect
scripts/
├── seed_skills.py             # 新增：由阶段2两份JSON生成 skills 字典种子（幂等）
└── init_db.py                 # 修改：追加 skills/user_skills/projects/user_preferences 建表
tests/
└── test_profile.py            # 新增：TC-P1~TC-P10
```

分层依赖（延续单向规则）：

```
API 层 api/routes/profile.py
   │  只调
   ▼
画像层 app/profile/（store ← skill_service ← extractor|rule_engine）
   │  只调
   ▼
持久化 app/persistence/db.py（psycopg）
```

**接线点（改动最小化）**
- `app/__init__.py` 的 `create_app`：注册 `profile_bp`。
- `app/config.py`：加 `PROFILE_*` 配置。
- `scripts/init_db.py`：追加四张表。
- `scripts/seed_skills.py`：生成技能字典种子。
- `docs/api_v1.md`：补画像四接口。

---

## 4. 模块解耦与分工

### 4.1 各模块职责、输入、输出、不负责什么

| 模块 | 职责 | 主要输入 | 主要输出 | 不负责什么 |
| --- | --- | --- | --- | --- |
| API 层（`routes/profile.py`） | 收 HTTP、校验、调画像层、包统一响应 | HTTP JSON | 统一 response | 不做抽取/规则/存储细节 |
| 抽取（`extractor.py`） | 自然语言/项目简介 → 结构化技能 patch | ProfileExtractionRequest + skills 字典 | SkillProfilePatch | 不写库、不算最终 level |
| 技能服务（`skill_service.py`） | 字典检索、归一化、等级换算、合并策略 | patch + 现有 profile | 合并后的 SkillProfile | 不调 LLM、不写 SQL |
| 规则引擎（`rule_engine.py`） | theory/practice→level、confidence 合并 | 分数 | level / confidence | 不做语义判断 |
| 存储（`store.py`） | user_skills/projects/preferences 读写 | config + 数据 | 查询/写入结果 | 不做业务判断 |

### 4.2 团队分工（阶段 3 建议 2~3 角色，可并行）

| 角色 | 负责模块 | 主要交付物 | 依赖 | 是否可并行 |
| --- | --- | --- | --- | --- |
| 平台/后端 | config、`routes/profile.py`、`store.py`、`init_db`、`seed_skills`、测试基线 | 建表+种子、四接口骨架 | 无（契约先行后并行） | 是 |
| 画像算法 | `skill_service.py`、`rule_engine.py`、`extractor.py` | 抽取/合并/等级换算走通 | 依赖契约 + 字典就绪 | 契约后并行 |
| 资料/测试 | `skills` 种子字典校验、`test_profile.py` | TC-P1~P10、样例语料 | 两端交付后联调 | 可先写契约断言与样例 |

> 并行关键是**先冻结契约**（第 5、6 节 schema），尤其 `SkillProfile` 与 `SkillProfilePatch` 的结构。

---

## 5. 输入 / 输出接口契约（Profile）★ 本阶段重点

> 复用阶段 1 统一规范：成功 `{"code":0,"message":"ok","data":...}`；错误带 `trace_id`；snake_case。新增错误码 `50020`（抽取失败，走兜底），`422xx`（校验失败）。

### 5.1 输出结构（先定"画像长什么样"）

**`SkillProfile`（一次成功的查询/合并所返回，也是阶段 4 的输入快照）**

```jsonc
{
  "user_id": "U10001",
  "version": 12,                                    // 每次增量更新 +1
  "updated_at": "2026-08-27T10:00:00Z",
  "skills": [
    {
      "skill_id": "java",                            // 对齐 skills 字典 id
      "name": "Java",
      "level": 4,                                    // 0~5，由规则引擎换算
      "theory_score": 80,                            // 0~100 理论分
      "practice_score": 85,                          // 0~100 实践分
      "confidence": 0.95,                            // 0~1
      "last_proven_at": "2026-08-20T00:00:00Z",
      "evidence": [ "MSG_001", "PROJ_003" ]          // 来源 id 列表
    }
  ],
  "projects": [
    { "project_id": "PROJ_003", "name": "订单系统", "skills": ["spring_boot", "mysql"] }
  ],
  "preferences": {
    "learning_style": "project_driven",
    "weekly_hours": 8
  }
}
```

**`SkillProfilePatch`（每次增量更新的载荷；只含要变更的技能）**

```jsonc
{
  "user_id": "U10001",
  "skills": [
    {
      "skill_id": "java",
      "theory_score": 82,                            // 覆盖或合并的分数（可空分别更新）
      "practice_score": 87,
      "confidence": 0.96,
      "evidence": [ "MSG_001" ]                      // 追加的证据 id
    }
  ],
  "preferences": { "learning_style": "project_driven" }
}
```

> **关键约束**：`SkillProfilePatch` 只表达"本次要变更的字段"，未提及的字段在合并时**保持不变**（G4）。`skills[]` 为空数组表示"本次无技能变更"。

**`SkillEvidence`（证据索引，松散数据结构）**

```jsonc
{ "evidence_id": "MSG_001", "user_id": "U10001",
  "source_type": "conversation",                      // conversation|self_report|project
  "source_ref": "THREAD_T20260826",                   // 支撑可追溯
  "claim": "我会 Java 和 Spring Boot，做过订单系统",
  "extracted_at": "2026-08-27T10:00:00Z" }
```

### 5.2 输入接口（HTTP 契约）

**5.2.1 POST /api/v1/profile/extract —— 从自然语言/项目简介抽取**

```jsonc
// 请求
{
  "user_id": "U10001",
  "source_type": "conversation",                      // conversation|self_report|project
  "source_ref": "THREAD_T20260826",                   // 可选，用于形成证据
  "content": "我会 Java、Spring Boot、MySQL，做过订单系统，Redis 也会用",
  "project_id": null                                  // 若提取自某个项目则带上
}

// 响应 200 data —— 返回"待确认"的 patch（不落库，先给前端/调用方确认）
{
  "status": "extracted",
  "patch": {
    "user_id": "U10001",
    "skills": [
      { "skill_id": "java", "theory_score": 78, "practice_score": 80, "confidence": 0.9,
        "evidence": ["MSG_001"] }
    ],
    "preferences": {}
  },
  "unmatched_tokens": ["做过订单系统"]                // 无法映射到技能字典的片段，便于回传
}
```

> `skill_id` 必须命中 `skills` 字典；未命中片段进 `unmatched_tokens` 而非静默丢弃（可追溯）。

**5.2.2 POST /api/v1/profile/upsert —— 合并增量更新（确认/手动登记）**

```jsonc
// 请求 = SkillProfilePatch（见 5.1）
// 响应 200 data = SkillProfile（合并后的完整画像）
{ "user_id": "U10001", "version": 13, "updated_at": "...",
  "skills": [/* 合并后全量 */], "projects": [], "preferences": { /* 合并后 */ } }
```

**5.2.3 GET /api/v1/profile/{user_id} —— 查询画像**

```jsonc
// 响应 200 data = SkillProfile；user 无画像时 skills=[]、version=0
```

**5.2.4 POST /api/v1/profile/projects —— 登记项目并绑定技能**

```jsonc
// 请求
{
  "user_id": "U10001",
  "project_id": "PROJ_003", "name": "订单系统",
  "description": "基于 Spring Boot + MySQL + Redis 的订单系统",
  "repo_url": null,
  "skills": ["spring_boot", "mysql"]                  // 可选：直接指定；否则后端从 description 抽取
}
// 响应 200 data = 更新后的 SkillProfile（含新 project 与并其技能合并进画像）
```

### 5.3 等级换算规则（rule_engine，非 LLM）

```
level = 0..5，由 theory/practice 加权：
  raw = 0.4 * theory_score + 0.6 * practice_score   // 实践权重更高（本阶段默认，PROFILE_* 可调）
  level = floor(raw / 20)  上限 5 ；低于下限行为 0
confidence 合并： pre := 旧置信度, inp := 新置信度
  merged = inp if pre is None else 0.4*pre + 0.6*inp   // 新证据更可信
```
> 规则集中、参数可配，保证同一输入结果稳定（G3、可重复），LLM 只负责"抽出什么技能"，不负责"打几分"。

### 5.4 增量更新合并策略（G4 的落地规则）

- **只处理 patch 中出现的 `skill_id`**：未出现的一律不动。
- 分数可空：patch 里某字段为 `null` 表示本次不更新该字段。
- 证据追加（不去重取决于 UI 需要）：
  - 已有证据与新增证据取并集；若 `force_replace_evidence: true` 则替换。
- `confidence` 用 5.3 的合并公式；`last_proven_at` 有新增证据才更新。
- 全部技能影响完后 `version = old_version + 1`。

### 5.5 配置输入（环境变量，`config.py` 新增）

| 环境变量 | 必填 | 说明 | 示例 |
| --- | --- | --- | --- |
| `PROFILE_PRACTICE_WEIGHT` | 否 | level 换算中实践权重 | `0.6` |
| `PROFILE_SOFT_CAP_SKILLS` | 否 | 单次提取最大技能数（防乱医学） | `30` |
| `PROFILE_MIN_CONFIDENCE` | 否 | 低于此置信度的技能不入画像 | `0.4` |
| `PROFILE_LLM_ENABLED` | 否 | 关闭则一律走规则兜底 | `true` |

---

## 6. 数据契约与存储

### 6.1 关系（对齐计划书 §8 的 V1 表）

```
skills(id, name, category, description)                      -- 技能字典（种子）
user_skills(user_id, skill_id, theory_score, practice_score,
            confidence, last_proven_at, updated_at, PK(user_id,skill_id))
projects(id, user_id, name, description, repo_url, skills text[], created_at)
user_preferences(user_id, key, value jsonb, updated_at, PK(user_id,key))
skill_evidence(id, user_id, source_type, source_ref, claim, extracted_at)
```

> `skill_evidence` 本阶段为**松散索引**（画像可追溯来源）；完整 Semantic/Episodic 记忆抽象留阶段 7。

### 6.2 建表 SQL（纳入 `scripts/init_db.py`，幂等）

```sql
CREATE TABLE IF NOT EXISTS skills (
  id          VARCHAR(64) PRIMARY KEY,
  name        VARCHAR(128) NOT NULL,
  category    VARCHAR(64),
  description TEXT
);
CREATE INDEX IF NOT EXISTS idx_skills_name ON skills(name);

CREATE TABLE IF NOT EXISTS user_skills (
  user_id       VARCHAR(64) NOT NULL,
  skill_id      VARCHAR(64) NOT NULL REFERENCES skills(id),
  theory_score  SMALLINT NOT NULL DEFAULT 0,      -- 0..100
  practice_score SMALLINT NOT NULL DEFAULT 0,
  confidence    REAL NOT NULL DEFAULT 0,
  last_proven_at TIMESTAMPTZ,
  updated_at    TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (user_id, skill_id)
);

CREATE TABLE IF NOT EXISTS projects (
  id          VARCHAR(64) PRIMARY KEY,
  user_id     VARCHAR(64) NOT NULL,
  name        VARCHAR(255),
  description TEXT,
  repo_url    TEXT,
  skills      TEXT[] DEFAULT '{}',
  created_at  TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_projects_user ON projects(user_id);

CREATE TABLE IF NOT EXISTS user_preferences (
  user_id    VARCHAR(64) NOT NULL,
  key        VARCHAR(64) NOT NULL,
  value      JSONB,
  updated_at TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (user_id, key)
);

CREATE TABLE IF NOT EXISTS skill_evidence (
  id           VARCHAR(64) PRIMARY KEY,
  user_id      VARCHAR(64) NOT NULL,
  source_type  VARCHAR(32),
  source_ref   VARCHAR(255),
  claim        TEXT,
  extracted_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_skill_evidence_user ON skill_evidence(user_id);
```

### 6.3 技能字典种子（`scripts/seed_skills.py`，幂等）

- 从阶段 2 的 `SkillPilot_skill_relations.json["skills"][].skill` 与 `SkillPilot_role_competencies.json["roles"][].required_skills[].skill` 归一（去空格/大小写）去重，写入 `skills`。
- `id` = 小写蛇形 slug（`spring_boot`、`vector_db`），显式 `--dry-run` 预览。
- `seed_skills.py` 只负责种子；运行时技能名归一由 `skill_service` 处理。

### 6.4 初始化时机（延续约定）

- **建表/种子**只在 `scripts/init_db.py` / `scripts/seed_skills.py`（迁移期）执行；**禁止**在业务路径重复 `CREATE` 或重复灌字典。

---

## 7. 功能清单

| # | 功能 | 关联目标 |
| --- | --- | --- |
| F1 | `skills/user_skills/projects/user_preferences/skill_evidence` 建表（init_db 幂等） | G1 |
| F2 | `seed_skills`：由阶段2两份JSON生成字典种子 | G1 |
| F3 | `POST /profile/extract`：LLM 结构化抽取 + 未命中片段回传 | G1/G2 |
| F4 | `POST /profile/upsert`：增量合并（只动 patch 提到的技能） | G4 |
| F5 | `GET /profile/{user_id}`：返回 `SkillProfile`（含 version） | G1 |
| F6 | `POST /profile/projects`：项目登记 + 简介抽取技能并合并画像 | G5 |
| F7 | 等级换算规则（theory/practice→level）与 confidence 合并 | G3 |
| F8 | LLM 不可用/失败时确定性兜底（空 skills + unmatched_tokens 全量） | G6 |
| F9 | `docs/api_v1.md` 补画像四接口 | G6 |
| F10 | `test_profile.py`（TC-P1~P10） | G6 |

---

## 8. 验收标准与测试用例

### 8.1 验收条件（全部满足即完成）

| 编号 | 验收项 | 验证方式 |
| --- | --- | --- |
| AC1 | 字典表就绪 | `init_db` + `seed_skills` 可重复；`\dt skills` 存在且有种子 |
| AC2 | 抽取可用 | `POST /profile/extract` 返回结构化 skills，含 theory/practice/confidence/evidence |
| AC3 | 等级可计算 | 同一 theory/practice 输入，`level` 输出稳定（规则，非 LLM 随意给分） |
| AC4 | 增量不覆盖 | upsert 只改 patch 提到的技能；未提到技能的分值不变 |
| AC5 | 项目技能关联 | 登记项目后，`projects.skills` 与画像 skills 同步合并 |
| AC6 | 兜底稳定 | LLM off/失败时仍返回标准结构（skills=[] + unmatched_tokens） |
| AC7 | 契约有测试 | TC-P1~P10 全绿 |

### 8.2 集成测试用例（`tests/test_profile.py`）

| 用例 | 输入 | 预期 |
| --- | --- | --- |
| TC-P1 空画像 | GET user 无画像 | 200，skills=[]、version=0 |
| TC-P2 规则换算 | theory=80,practice=85 | level=4（0.4*80+0.6*85=83→floor(83/20)=4） |
| TC-P3 基础 upsert | patch 一段技能 | 画像含该技能且 version+1 |
| TC-P4 增量不覆盖 | 第二次 patch 只提 A，不提已存在 B | B 不变，A 更新 |
| TC-P5 null 字段不更新 | patch 里 practice_score=null | practice_score 保持旧值 |
| TC-P6 confidence 合并 | pre=0.9,inp=0.5 | merged=0.4*0.9+0.6*0.5=0.66 |
| TC-P7 证据关联 | extract 后 skills[].evidence 含 evidence_id | evidence 列表正确合并/追加 |
| TC-P8 项目登记+抽技 | 登记项目 description 含技术词 | projects.skills 与画像合并 |
| TC-P9 LLM 兜底 | PROFILE_LLM_ENABLED=off | 返回 skills=[] + unmatched_tokens 全量，200 |
| TC-P10 非法入参 | user_id 非法 / content 空 | 422 + code 42200 + trace_id |

> TC-P6 与 TC-P9 不依赖真实 LLM，用规则与 `off` 配置稳定复现。

---

## 9. 任务拆解与并行分工

### 9.1 前置（契约对齐，先做）

- [ ] 冻结第 5 节 schema：`SkillProfile` / `SkillProfilePatch` / `SkillEvidence` / 等级规则参数
- [ ] 确认技能字典归一规则（slug 规则、中外文技能名去重）
- [ ] 确认 seed_skills 输入两份 JSON 的路径与字段

### 9.2 平台/后端（与画像算法并行）

1. `init_db.py` 追加四张表（skills/user_skills/projects/user_preferences/skill_evidence）
2. `seed_skills.py`：字典种子（幂等 + dry-run）
3. `config.py` 加 `PROFILE_*`
4. `store.py`：四张表读写（psycopg 直连）
5. `routes/profile.py` 四接口骨架 + 注册 `profile_bp`
6. 测试基线：画像契约断言工具

### 9.3 画像算法（契约后并行）

1. `rule_engine.py`：level 换算 + confidence 合并
2. `skill_service.py`：字典检索/归一 + 合并策略
3. `extractor.py`：LLM 结构化抽取 + 兜底 + unmatched 回传
4. 与后端联调四接口

### 9.4 资料/测试

1. 校验 seed 字典（与阶段2两份JSON字段对齐）
2. 样例语料：自述/项目简介 → 期望 patch
3. 实现 TC-P1~P10
4. 输出验收核对清单（AC1~AC7）

### 9.5 里程碑

| 里程碑 | 内容 | 完成标志 |
| --- | --- | --- |
| M1 | 契约冻结 + 字典种子 | schema 签署、seed_skills 可跑出字典 |
| M2 | 库表/种子就绪 | `\dt skills|user_skills|projects` 存在含种子 |
| M3 | 抽取走通 | extract 返回结构化 patch |
| M4 | 增量更新走通 | upsert 合并正确、version+1 |
| M5 | 项目关联走通 | projects 登记后画像合并 |
| M6 | 测试与文档 | TC-P1~P10 全绿 + api_v1.md 更新 |

---

## 10. 风险与注意事项

| 风险 | 表现 | 应对 |
| --- | --- | --- |
| LLM 抽取不稳定 | 技能名漂移/乱建 id | 强制命中 `skills` 字典；未命中进 unmatched；等级用规则 |
| 技能字典与阶段2图谱漂移 | seed 与 relations 不一致 | `seed_skills` 由两份 JSON 生成，单一来源；运行时归一 |
| 增量更新误覆盖 | 无关技能分值被动 | 只处理 patch 出现的 skill_id；null 字段不更新（TC-P4/P5守护） |
| 置信度合并偏差 | 旧证据被低估 | 采用 0.4/0.6 合并公式，保留 last_proven_at |
| 评分不可重复 | level 抖动 | 等级只由规则算，不让 LLM 给分 |
| 中文/英文技能名 | 同名映射失败 | skill_service 做归一（拼音/别名表可选） |

---

## 11. 交付物清单（阶段 3）

- [ ] `skills` / `user_skills` / `projects` / `user_preferences` / `skill_evidence` 表（init_db 幂等）
- [ ] `seed_skills.py`：技能字典种子（由阶段 2 两份 JSON 生成）
- [ ] `app/profile/`：schemas / skill_service / extractor / store / rule_engine
- [ ] 四接口：`POST /profile/extract | upsert | projects`、`GET /profile/{user_id}`
- [ ] `SkillProfile` 输出结构 + 等级换算规则 + 增量合并策略
- [ ] `config.py` `PROFILE_*` 配置 + `50020` 抽取兜底错误码
- [ ] `docs/api_v1.md` 增补画像契约
- [ ] `tests/test_profile.py`（TC-P1~P10）全绿
- [ ] 验收核对清单（AC1~AC7）

> **对接下一阶段**：阶段 4 的 `GapAnalysisRequest.current_profile_version` 直接取本阶段 `SkillProfile.version`；画像即阶段 4 的确定性输入快照。