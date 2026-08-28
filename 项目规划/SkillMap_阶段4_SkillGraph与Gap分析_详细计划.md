# SkillMap 阶段 4 详细实施计划 — Skill Graph 与 Gap Analysis

> 对应：《SkillMap_个人技术栈成长智能体_项目计划书》阶段 4"Skill Graph 与 Gap Analysis"
> 版本：V1.0
> 风格：模块解耦 + 契约先行 + 并行开发（与阶段 2、3 详细计划保持一致的行文规范）

---

## 1. 阶段定位与目标

**一句话目标**：建立技能节点与依赖图（Skill Graph），输入"用户画像 + 目标岗位/目标能力"，输出**结构化、带优先级、可解释、可重复**的能力缺口报告（`SkillGapReport`）。

**为什么必须先做阶段 4**：阶段 3 产出"用户现在会什么"，但用户需要知道"为达到某个岗位还差什么、先补什么"。缺口不是简单差集——同一岗位，缺失前沿技能与缺失前置基础的意义不同；同一个人选不同岗位得到不同缺口。只有把技能依赖（`requires`/`composite_of`）与岗位要求（`role_skills`）建成可查询的图，才能给出"为什么先学 X 再学 Y"的可解释结论，供阶段 5 生成有依赖、可排序的学习路线。

**本阶段核心目标拆解**

| # | 目标 | 验收可测性 |
| --- | --- | --- |
| G1 | 技能图就绪 | `seed_skill_graph` 建出 skill_nodes/skill_edges/role_skills，幂等 |
| G2 | 缺口可算 | 画像+目标岗位 → `SkillGapReport`，含缺失技能清单 |
| G3 | 缺口可解释 | 每个缺口有 `priority/score/reason`，能给出前置链 |
| G4 | 岗位差异 | 同一用户选不同岗位得到不同缺口 |
| G5 | 评分可重复 | $score$ 等结构化字段纯规则计算，不依赖 LLM 结果 |
| G6 | 契约稳定 + 兜底 | 有测试；LLM 关闭/失败仍返回结构化 report |

---

## 2. 范围边界

### 2.1 本阶段做什么（In Scope）

- 建表：`skill_nodes` / `skill_edges` / `role_skills`
- `seed_skill_graph.py`：由阶段 2 两份 JSON（`SkillPilot_skill_relations.json` + `SkillPilot_role_competencies.json`）生成三张表（幂等 + dry-run）
- `GapScore`：技能缺口评分规则（可重复）
- 前置关系闭包查询：`requires` 传递闭包 + 拓扑排序
- `Gap Agent`：检索画像 → 叠目标 → 计算 → 组 report
- `POST /api/v1/gap/request` 接口
- 5 个典型目标岗位测试集（覆盖 AI/后端/架构/数据）
- 契约文档 + 集成测试（TC-G1~G10）

### 2.2 本阶段明确不做（Out of Scope）

| 不做 | 原因 | 何时做 |
| --- | --- | --- |
| 学习计划生成 | 把缺口转成可执行路线 | 阶段 5 |
| Todo 中间件、进度恢复 | 任务持有与流转 | 阶段 5 |
| 评估/画像自动更新 | 由证据闭环触发再计算 | 阶段 6 |
| 完整长期记忆 | 缺口的记忆化 | 阶段 7 |
| 前端 Gap 可视化页 | 后端契约先行 | 阶段 8 |
| 精确 LLM 润色解释（可选建议） | 结构化字段已可解释，LLM 润色不作为核心依赖 | 按需后置 |

> 边界原则（对齐计划书）：MVP 先做"规则可重复的缺口计算 + 前置可解释"；LLM 仅用于润色 `suggestions`，**结构、评分、优先级都不依赖 LLM**。

---

## 3. 技术选型与工程结构

### 3.1 技术栈（阶段 2、3 基础上，无新增依赖）

| 项 | 选型 | 说明 |
| --- | --- | --- |
| 存储 | PostgreSQL（复用 `psycopg` 直连） | 沿用既有风格 |
| 图模型 | 关系表 `skill_edges` + 应用层 BFS/拓扑 | 数据量在数百节点级，不引入图数据库 |
| 规则 | 纯 Python（GapScore、闭包、排序） | G5 可重复 |
| LLM | 仅 `suggestions` 润色，复用阶段 1 `LLMClient` | 失败走模板兜底 |

### 3.2 工程结构（新增/修改点）

```
app/
├── config.py                 # 修改：新增 GAP_* 配置（可选）
├── api/routes/
│   ├── gap.py                # 新增：POST /api/v1/gap/request
│   └── __init__.py           # 修改：注册 gap_bp
├── gap/                      # 新增：【缺口层】不感知 HTTP
│   ├── __init__.py
│   ├── schemas.py            # 契约：GapAnalysisRequest / SkillGapReport / GapItem
│   ├── graph_store.py        # skill_nodes/skill_edges/role_skills 读取
│   ├── gap_score.py          # GapScore 规则（可重复）
│   ├── closure.py            # requires 传递闭包 + 拓扑排序
│   ├── gap_agent.py          # 编排：画像+目标 → 缺口 → report（含可选 LLM 润色）
│   └── explain.py            # reason 模板生成（默认，不依赖 LLM）
└── persistence/
    └── ...                   # 复用 db.connect
scripts/
├── seed_skill_graph.py       # 新增：三张表种子（幂等 + dry-run）
└── init_db.py                # 修改：追加 skill_nodes/skill_edges/role_skills 建表
tests/
└── test_gap.py               # 新增：TC-G1~G10 + 5 岗位测试集
```

分层依赖（延续单向规则）：

```
API 层 api/routes/gap.py
   │  只调
   ▼
缺口层 app/gap/（graph_store ← closure|gap_score ← gap_agent｜explain）
   │  只调
   ▼
持久化 app/persistence/db.py
```

**接线点（改动最小化）**
- `app/__init__.py`：注册 `gap_bp`。
- `scripts/init_db.py`：追加三张表。
- `scripts/seed_skill_graph.py`：种子。
- `docs/api_v1.md`：补 gap 接口。

---

## 4. 模块解耦与分工

### 4.1 各模块职责、输入、输出、不负责什么

| 模块 | 职责 | 主要输入 | 主要输出 | 不负责什么 |
| --- | --- | --- | --- | --- |
| API 层（`routes/gap.py`） | 收 HTTP、校验、调缺口层、统一响应 | HTTP JSON | 统一 response | 不做图/评分细节 |
| 图存储（`graph_store.py`） | 读 nodes/edges/role_skills | config + role_id/skill | 邻接表/岗位要求 | 不算分、不判断业务 |
| 评分（`gap_score.py`） | $score$/priority 规则 | required + current level | gap 项评分 | 不查图、不调 LLM |
| 闭包（`closure.py`） | requires 传递闭包 + 拓扑排序 | edges + skills | 前置链 + 学习序列 | 不算分 |
| 缺口编排（`gap_agent.py`） | 画像+目标→缺口→report | GapAnalysisRequest | SkillGapReport | 不写库、不写 HTTP |
| 解释（`explain.py`） | reason 模板 / LLM 润色 | gap 规则结果 | 可读 reason / suggestions | 不决策优先级 |

### 4.2 团队分工（阶段 4 建议 2~3 角色）

| 角色 | 负责模块 | 主要交付物 | 依赖 | 是否可并行 |
| --- | --- | --- | --- | --- |
| 平台/后端 | config、`routes/gap.py`、`graph_store.py`、`init_db`、`seed_skill_graph`、测试基线 | 三表+种子、接口骨架 | 无（契约先行） | 是 |
| 缺口算法 | `gap_score.py`、`closure.py`、`explain.py`、`gap_agent.py` | 评分/闭包/编排走通 | 契约 + 图种子 | 契约后并行 |
| 资料/测试 | 5 岗位测试集、`test_gap.py` | TC-G1~G10、岗位样例 | 两端交付后联调 | 可先写岗位断言 |

> 并行关键是**先冻结第 5、6 节 schema**（尤其 `SkillGapReport` 输出结构）。

---

## 5. 输入 / 输出接口契约（Gap）★ 重点

> 复用统一规范：成功 `{"code":0,"data":...}`；错误带 `trace_id`；snake_case。新增错误码 `50030`（缺口计算失败，走兜底）。

### 5.1 输入结构：`GapAnalysisRequest`

```jsonc
// POST /api/v1/gap/request
{
  "user_id": "U10001",
  "target_roles": ["RC002"],        // 目标岗位 ID（可多个，各产出一份 report）
  "target_skills": null,            // 二选一：或直接用目标能力集合（后端自动构造临时岗位要求）
  // 形如 [ {"skill":"LangGraph","level":4,"weight":1.0}, ... ]
  "profile_version": 12,            // 可选：指定使用的画像版本（用于校验/锁定）
  "top_gaps": 50                    // 可选：最多返回缺口数，默认全部
}
```
> 约束：`target_roles` 与 `target_skills` **至少提供一个**；都提供时以 `target_roles` 为主、`target_skills` 视为额外追加要求（供"角色+个人增补技能"混合场景）。

### 5.2 输出结构：`SkillGapReport` ★（阶段 4 核心产物，也是阶段 5 输入）

```jsonc
{
  "user_id": "U10001",
  "target_role_id": "RC002",
  "target_role": "AI Agent 工程师",
  "role_category": "AI/Application",
  "profile_version_used": 12,
  "generated_at": "2026-08-27T12:00:00Z",
  "is_llm_enhanced": true,                  // suggestions 是否由 LLM 润色；false=模板兜底

  "coverage": {
    "required_total": 8,
    "covered_skills": ["python"],           // 已达要求的技能 id
    "gap_skills": ["langgraph", "llm_api", ...],
    "gap_total": 5,
    "coverage_rate": 0.375                 // covered/required
  },

  "gaps": [
    {
      "skill_id": "langgraph",
      "name": "LangGraph",
      "required_level": 4,
      "current_level": 0,
      "required_weight": 1.0,
      "score": 0.8,                          // GapScore，可重复，见 5.3
      "priority": "P1",
      "reason": "岗位核心编排技能（weight 1.0）缺失，等级差 4 级",
      "prerequisites": [                     // requires 传递展开
        {"skill_id": "python", "name": "Python",        "status": "gap",    "own_gap_id": null},
        {"skill_id": "langchain", "name": "LangChain",  "status": "gap",    "own_gap_id": "langchain"},
        {"skill_id": "llm_api", "name": "LLM API",      "status": "gap",    "own_gap_id": "llm_api"}
      ],
      "recommended_sequence": ["python", "llm_api", "langchain", "langgraph"]
    }
  ],

  "recommended_sequence": [                 // 全部缺口按前置关系拓扑排序
    "python", "llm_api", "langchain", "langgraph", "rag", "vector_db", ...
  ],

  "suggestions": "先从 Python/LLM API 补齐基础，按 langgraph 的前置链逐层推进……"
}
```

> **字段语义要点**
> - `gaps` 只含**真实缺口**（当前等级未达到要求等级的 role_skills 技能或其缺失前置）。
> - `prerequisites[].own_gap_id`：若某前置本身也在 `gaps` 中（即也是缺口），指向其自身 entry，便于前端点对点跳转；非缺口前置为 `null`。
> - `score / priority / reason / prerequisites / recommended_sequence` 均由规则计算（可重复）；仅 `suggestions` 可由 LLM 润色。

### 5.3 GapScore 规则（gap_score，纯规则）

```
对每个岗位要求技能 r（required_level=Lr, weight=w_r），取用户当前等级 Lu（缺失视为 0）：
  delta       = max(0, Lr - Lu)
  covered     = (Lu >= Lr)
  score       = round( w_r * (delta / 5.0), 3 )        # 归一 0..1（w≤1, delta≤5）
  priority:
      covered            -> 不计入 gaps
      w_r >= 0.9 且 delta>=2 -> P1   # 核心缺失
      w_r >= 0.7            -> P2
      其他                -> P3
  缺失前置的技能（非岗位直接要求）占位进入 gaps，score 按其被引用技能权重传递（×0.5 衰减）

reason 模板（explain，不依赖 LLM）：
  f"{name}：岗位要求 level {Lr}，当前 level {Lu}，{描述}（weight {w_r}）"
  若存在前置缺失，追加"需先完成前置：{前置名列表}"
```
> 规则集中、参数可配（`GAP_*`），同一输入结果严格一致（TC-G6 守护），LLM 不参与 score/priority。

### 5.4 前置闭包与排序（closure）

- 读入 `skill_edges` 中 `relation='requires'` 的有向边（`requires`：A 需要 B ⇒ 边 B→A 为前置）。
- 对每个岗位要求技能：沿前置反向 BFS 得**传递闭包**，过滤掉用户已掌握与已在角色要求集合内者，得缺失前置集。
- `recommended_sequence`：对"岗位要求缺口 + 缺失前置"以**拓扑排序**（前置者先），环用去重兜底（仅保留一次）。
- 目的：回答"为什么先学 LangChain 再学 LangGraph"（前置链），支撑阶段 5 生成有序计划。

### 5.5 配置输入（`config.py` 可选新增）

| 环境变量 | 必填 | 说明 | 示例 |
| --- | --- | --- | --- |
| `GAP_TOP_DEFAULT` | 否 | 默认最大返回缺口数 | `50` |
| `GAP_PREREQ_DECAY` | 否 | 缺失前置降权系数 | `0.5` |
| `GAP_LLM_ENABLED` | 否 | 是否用 LLM 润色 suggestions | `true` |

---

## 6. 数据契约与存储

### 6.1 三张表（纳入 `scripts/init_db.py`，幂等）

```sql
CREATE TABLE IF NOT EXISTS skill_nodes (
  id          VARCHAR(64) PRIMARY KEY,
  name        VARCHAR(128) NOT NULL,
  domain      VARCHAR(64),
  description TEXT
);
CREATE INDEX IF NOT EXISTS idx_skill_nodes_name ON skill_nodes(name);

CREATE TABLE IF NOT EXISTS skill_edges (
  source VARCHAR(64) NOT NULL REFERENCES skill_nodes(id),
  target VARCHAR(64) NOT NULL REFERENCES skill_nodes(id),
  rel    VARCHAR(32) NOT NULL,            -- composite_of | requires | related
  PRIMARY KEY (source, target, rel)
);
CREATE INDEX IF NOT EXISTS idx_skill_edges_rel ON skill_edges(rel);

CREATE TABLE IF NOT EXISTS role_skills (
  role_id   VARCHAR(64) NOT NULL,
  role_name VARCHAR(128),
  category  VARCHAR(64),
  skill_id  VARCHAR(64) NOT NULL REFERENCES skill_nodes(id),
  level     SMALLINT NOT NULL,            -- 0..5
  weight    REAL NOT NULL DEFAULT 1.0,
  reason    VARCHAR(255),
  PRIMARY KEY (role_id, skill_id)
);
CREATE INDEX IF NOT EXISTS idx_role_skills_role ON role_skills(role_id);
```

### 6.2 种子（`scripts/seed_skill_graph.py`，幂等 + dry-run）

- `skill_nodes`：由 `SkillPilot_skill_relations.json["skills"][].skill` 与 `SkillPilot_role_competencies.json` 全部 required_skills.skill 归一去重。
- `skill_edges`：由 relations 的 `composite_of/requires/related`（source=技能, target=被跟随能力）逐条 upsert 入 `rel`。
- `role_skills`：由 role_competencies 的每个 `role.required_skills[]`（skill/level/weight/reason + role_id/role/category）写入。
- 节点/边为缺省补齐：relations 中作为前置出现但不在 `skills[]` 里的名称（如"编程基础"）也建节点（`description` 标注"来自关系图隐式节点"）。
- `--dry-run` 预览；重跑只 update 不重复。

### 6.3 初始化时机（延续约定）

- 建表/种子仅在迁移期执行；**禁止**在 gap 计算路径内重复 `CREATE` 或重复灌图。

---

## 7. 功能清单

| # | 功能 | 关联目标 |
| --- | --- | --- |
| F1 | skill_nodes/skill_edges/role_skills 建表（init_db 幂等） | G1 |
| F2 | seed_skill_graph（由两份JSON生成，幂等+dry-run） | G1 |
| F3 | GapScore（score/priority 规则） | G3/G5 |
| F4 | requires 传递闭包 + 拓扑排序 | G3 |
| F5 | Gap Agent 编排（画像+目标→report） | G2/G4 |
| F6 | 岗位差异（target_roles/target_skills 混合） | G4 |
| F7 | reason 模板解释（explain，不依赖 LLM） | G3 |
| F8 | suggestions LLM 润色 + 模板兜底 | G6 |
| F9 | `docs/api_v1.md` 补 gap 接口 | G6 |
| F10 | `test_gap.py`（TC-G1~G10 + 5 岗位测试集） | G6 |

---

## 8. 验收标准与测试用例

### 8.1 验收条件（全部满足即完成）

| 编号 | 验收项 | 验证方式 |
| --- | --- | --- |
| AC1 | 图/岗种子就绪 | `init_db`+`seed_skill_graph` 可重复；三表有数据 |
| AC2 | 缺口可算 | input 画像+岗位 → report 含 `gaps[]` 与 `coverage` |
| AC3 | 缺口可解释 | 每个 `gap` 有 `priority/score/reason` 且非空 |
| AC4 | 岗位差异 | 同一用户选不同岗位 → `gaps` 不同 |
| AC5 | 评分可重复 | 同一输入两次计算字段一致，不依赖 LLM 结果 |
| AC6 | 版本/契约 | `profile_version_used` 正确；非法入参 422 |
| AC7 | 契约有测试 | TC-G1~G10 全绿 + 5 岗位测试集通过 |

### 8.2 集成测试用例（`tests/test_gap.py`）

| 用例 | 输入 | 预期 |
| --- | --- | --- |
| TC-G1 种子完备 | seed 后查三表 | nodes 数=relations+岗位技能去重；edges 含 requires/composite/related；role_skills 含 30 岗位 |
| TC-G2 岗位差异 | 同一 user 对 RC002 vs RC010 | gaps 技能集合不同 |
| TC-G3 覆盖不入缺 | 已会技能达到要求 | 不出现在 gaps；coverage 计入 |
| TC-G4 字段齐全 | 任一 gap | priority ∈{P1,P2,P3}、score∈[0,1]、reason 非空 |
| TC-G5 前置闭包 | RC002 缺 LangGraph | prereq 展开含 python/langchain/llm_api；recommended_sequence 拓扑有序 |
| TC-G6 评分可重复 | 同请求两次 | score/priority 逐字段相等 |
| TC-G7 版本字段 | request 带 profile_version | report.profile_version_used 与之对应 |
| TC-G8 非法入参 | 无 roles 无 skills | 422 + code 42200 + trace_id |
| TC-G9 LLM 兜底 | GAP_LLM_ENABLED=off | 仍返回结构化 report，is_llm_enhanced=false |
| TC-G10 5 岗位测试集 | RC001/RC002/RC010/RC025/RC008 | 各 report.gap_total>0 且每 gap 含 reason |

> 5 个典型目标岗位：AI 应用工程师（RC001）、AI Agent 工程师（RC002）、Java 后端工程师（RC010）、企业级系统架构师（RC025）、数据分析师（RC008）——覆盖 AI/后端/架构/数据域，均来自 `role_competencies` 真实岗位。

---

## 9. 任务拆解与并行分工

### 9.1 前置（契约对齐，先做）

- [ ] 冻结第 5 节 schema：`SkillGapReport` / `GapItem` / `GapAnalysisRequest` 与 GapScore 参数
- [ ] 确认 seed_skill_graph 输入两份 JSON 路径与字段（复用阶段 3 的 `seed_skills` 归一规则）
- [ ] 确认 5 个测试岗位 id 与画像样例

### 9.2 平台/后端（与缺口算法并行）

1. `init_db.py` 追加三张表
2. `seed_skill_graph.py`：三表种子（幂等+dry-run）
3. `config.py` 加 `GAP_*`
4. `graph_store.py`：三表读取
5. `routes/gap.py` 接口骨架 + 注册 `gap_bp`
6. 测试基线：缺口契约断言工具

### 9.3 缺口算法（契约后并行）

1. `gap_score.py`：GapScore/priority
2. `closure.py`：传递闭包 + 拓扑排序
3. `explain.py`：reason 模板（默认不依赖 LLM）
4. `gap_agent.py`：编排 + `suggestions` LLM 润色（可选）
5. 与后端联调接口

### 9.4 资料/测试

1. 5 个典型岗位样例（画像 → 期望缺口）
2. 实现 TC-G1~G10
3. 输出验收核对清单（AC1~AC7）

### 9.5 里程碑

| 里程碑 | 内容 | 完成标志 |
| --- | --- | --- |
| M1 | 契约冻结 + 图种子 | schema 签署、seed_skill_graph 可出图 |
| M2 | 图/岗表就绪 | `\dt skill_nodes|skill_edges|role_skills` 含数据 |
| M3 | 缺口算通 | gap/request 返回 report |
| M4 | 前置可解释 | recommended_sequence 拓扑有序、reason 完整 |
| M5 | 岗位差异+重复性 | TC-G2/G6 通过 |
| M6 | 测试与文档 | TC-G1~G10 全绿 + api_v1.md 更新 |

---

## 10. 风险与注意事项

| 风险 | 表现 | 应对 |
| --- | --- | --- |
| 岗位名/技能名漂移 | role_skills 关联失败 | seed 统一走 `seed_skills` 的 `_slug`；缺省补节点 |
| 图有环 | 闭包/拓扑死循环 | 访问集去重 + 拓扑遇环做去重兜底（TC 覆盖） |
| 评分依赖 LLM | 结果抖动 | score/priority/reason 全走规则；LLM 只润色 suggestions |
| 前置过深/过多 | recommended_sequence 爆炸 | 只展开到岗位要求技能的前置闭包；数量上限 `GAP_*` |
| 无画像 | 全技能算 0 级 | 明确"缺失=0 级"，report 仍完整（coverage_rate 低） |
| 缓存/版本不一致 | 用了旧画像 | 返回 `profile_version_used`，接口可传 `profile_version` 校验 |

---

## 11. 交付物清单（阶段 4）

- [ ] `skill_nodes` / `skill_edges` / `role_skills` 表（init_db 幂等）
- [ ] `seed_skill_graph.py`：由阶段 2 两份 JSON 生成图与岗位要求（幂等 + dry-run）
- [ ] `app/gap/`：graph_store / gap_score / closure / gap_agent / explain
- [ ] `POST /api/v1/gap/request` 接口
- [ ] `SkillGapReport` 输出结构 + GapScore 规则 + 前置闭包/拓扑
- [ ] `config.py` `GAP_*` 配置 + `50030` 缺口错误码
- [ ] `docs/api_v1.md` 增补 gap 契约
- [ ] `tests/test_gap.py`（TC-G1~G10）+ 5 岗位测试集全绿
- [ ] 验收核对清单（AC1~AC7）

> **对接下一阶段**：阶段 5 的 `LearningPlan` 直接消费 `SkillGapReport.recommended_sequence` 与 `gaps[].recommended_sequence`，把有序缺口转成有前置依赖的学习任务。