# SkillPilot Agent 系统架构设计方案

## 1. 项目目标

SkillPilot 计划从当前的“对话 + 学习计划”应用，升级为一个围绕用户技术成长闭环工作的 Agent 系统。

核心目标是：

> 用户通过自然语言描述学习目标或求职目标，系统识别用户意图，拆解目标所需技能，基于技能知识图谱建立目标技能模型，再通过对话逐步了解用户当前技术栈，最终形成用户技能画像，并计算技能缺口，输出针对性的学习或求职建议。

核心设计原则：

> **Agent 负责理解和决策，数据结构负责描述事实，Skill Graph 负责推理。**

这样可以避免让多个 Agent 各自维护一套技能逻辑，降低后期系统复杂度。

---

## 2. 当前项目架构

当前仓库的核心流程仍然是：

```text
START
  ↓
orchestrator_agent
  ↓
intent
  ├── chat
  └── plan_generation
        ↓
     plan_agent
        ↓
      reply
```

当前 `contracts.py` 中仅保留：

```python
INTENT_HINTS = Literal[
    "plan_generation",
    "chat",
]
```

当前仓库已经具备一些非常重要的基础数据：

- `SkillPilot_role_competencies.json`：岗位能力知识库
- `SkillPilot_skill_relations.json`：技能关系知识库
- `SkillPilot_knowledge_sources.json`：知识与学习资源知识库

因此，新架构不需要从零开始建立知识层，而应该在现有基础上重新组织 Agent 和数据契约。

---

## 3. 新系统总体架构

建议将系统升级为以下结构：

```text
                         ┌───────────────┐
                         │     User      │
                         └───────┬───────┘
                                 │
                                 ▼
                       ┌──────────────────┐
                       │  IntentRouter    │
                       │      Agent       │
                       └────────┬─────────┘
                                │
              ┌─────────────────┼─────────────────┐
              │                 │                 │
              ▼                 ▼                 ▼
           CHAT          TECH_LEARNING        JOB_SEARCH
              │                 │                 │
              │                 ▼                 ▼
              │       TechRequirementAgent   JobRequirementAgent
              │                 │                 │
              │                 ▼                 ▼
              │          ┌─────────────────────────┐
              │          │   Target Skill Profile  │
              │          └────────────┬────────────┘
              │                       │
              │                       ▼
              │              Skill Interview Agent
              │                       │
              │                       ▼
              │                User Skill Profile
              │                       │
              │                       ▼
              │                  Gap Engine
              │                       │
              │              ┌────────┴─────────┐
              │              ▼                  ▼
              │        Learning Plan       Job Matching
              │
              ▼
         Chat Agent
```

知识层独立存在：

```text
              ┌──────────────────────────┐
              │      Knowledge Base      │
              │                          │
              │ Skill Dictionary         │
              │ Skill Relations          │
              │ Role Competencies        │
              │ Learning Resources       │
              └──────────┬───────────────┘
                         │
              ┌──────────┴──────────┐
              ▼                     ▼
        Skill Graph             Role Graph
```

所有 Agent 统一访问知识层，而不是自己维护技能知识。

---

## 4. 顶层意图分类

第一层建议只负责识别用户当前需求，不承担复杂业务处理。

### 4.1 Intent 枚举

```python
from enum import Enum


class IntentType(str, Enum):
    CHAT = "chat"
    TECH_LEARNING = "tech_learning"
    JOB_SEARCH = "job_search"
```

三类核心意图：

| 意图 | 示例 | 后续流程 |
|---|---|---|
| `chat` | “你好”“Python 是什么” | 普通对话 |
| `tech_learning` | “我想学习 LangGraph” | 技术需求拆解 |
| `job_search` | “我想找 AI Agent 工程师岗位” | 岗位需求拆解 |

### 4.2 IntentResult

```python
class IntentResult(BaseModel):
    intent: IntentType
    confidence: float
    reason: str | None = None
```

第一版不需要设计过多意图层级，保持简单、稳定即可。

---

## 5. 技术需求 Agent

技术需求 Agent 的职责不是直接给用户讲技术，而是：

> 将用户表达的学习目标转换成结构化的目标技能需求。

例如：

```text
用户：
我想学习 LangGraph

        ↓

TechRequirementAgent

        ↓

TechRequirement
```

### 5.1 TechRequirement

```python
class TechRequirement(BaseModel):
    goal: str
    target_skills: list[str]
    related_skills: list[str]
    prerequisites: list[str]
    context: str | None = None
```

例如：

```json
{
  "goal": "学习 LangGraph",
  "target_skills": [
    "LangGraph"
  ],
  "related_skills": [
    "LangChain",
    "Tool Calling",
    "RAG"
  ],
  "prerequisites": [
    "Python",
    "LLM API"
  ]
}
```

### 5.2 不建议由 LLM 直接猜全部技能

推荐流程：

```text
用户自然语言
    ↓
LLM 识别目标技能
    ↓
Skill Graph 查询
    ↓
requires
composite_of
related
    ↓
形成 Target Skill Profile
```

例如当前知识库中已经存在类似：

```text
LangGraph
├── requires
│   ├── Python
│   ├── LLM API
│   └── LangChain
│
├── composite_of
│   ├── State Management
│   ├── Checkpoint
│   └── Node/Graph 编排
│
└── related
    ├── Tool Calling
    └── RAG
```

这样可以减少大模型幻觉，并保证技能关系来源统一。

---

## 6. 岗位需求 Agent

岗位需求 Agent 与技术需求 Agent 的区别在于：

- 技术需求：用户明确要学习什么
- 岗位需求：用户明确想从事什么工作

例如：

```text
用户：
我想找一个 AI Agent 开发的工作

        ↓

JobRequirementAgent

        ↓

AI Agent 工程师

        ↓

Role Knowledge Base
```

### 6.1 JobRequirement

```python
class JobRequirement(BaseModel):
    role_id: str
    role_name: str
    target_level: str | None
    required_skills: list[SkillRequirement]
```

### 6.2 直接复用现有岗位知识库

当前 `SkillPilot_role_competencies.json` 已经提供岗位与技能的映射。

例如 AI Agent 工程师可以包含：

```text
LangGraph        level 4
LLM API          level 4
Python           level 4
Prompt Engineering level 4
RAG              level 3
Tool Calling     level 4
State Management level 3
Vector DB        level 2
```

JobRequirementAgent 主要负责：

```text
自然语言
   ↓
岗位识别
   ↓
role_id
   ↓
Role Knowledge Base
   ↓
required_skills
```

---

## 7. 统一 SkillRequirement

无论用户是：

- 想学 Python
- 想学 LangGraph
- 想学 RAG
- 想找 AI Agent 工程师
- 想找 Java 后端岗位

最终都应该转换成统一的技能需求结构。

```python
class SkillRequirement(BaseModel):
    skill_id: str
    skill_name: str
    required_level: int = Field(ge=0, le=5)
    weight: float = Field(ge=0, le=1)
    reason: str | None = None
    source: str | None = None
```

这样可以把不同业务入口统一到同一套技能模型。

---

## 8. Target Skill Profile

技术需求和岗位需求最终应该统一生成目标技能画像。

例如：

```python
class TargetProfile(BaseModel):
    goal_type: str
    goal_name: str
    skills: list[SkillRequirement]
```

技术目标示例：

```json
{
  "goal_type": "tech_learning",
  "goal_name": "LangGraph",
  "skills": [
    {
      "skill_name": "Python",
      "required_level": 2
    },
    {
      "skill_name": "LLM API",
      "required_level": 2
    },
    {
      "skill_name": "LangChain",
      "required_level": 2
    },
    {
      "skill_name": "LangGraph",
      "required_level": 3
    }
  ]
}
```

岗位目标示例：

```json
{
  "goal_type": "job_search",
  "goal_name": "AI Agent 工程师",
  "skills": [
    {
      "skill_name": "Python",
      "required_level": 4
    },
    {
      "skill_name": "LLM API",
      "required_level": 4
    },
    {
      "skill_name": "LangGraph",
      "required_level": 4
    },
    {
      "skill_name": "Tool Calling",
      "required_level": 4
    }
  ]
}
```

这样后续能力评估、缺口计算与学习计划不再需要区分用户最开始的入口。

---

## 9. Skill Interview Agent

这是系统中最重要的 Agent 之一。

它的职责不是“考试”，而是通过多轮自然对话建立用户技术栈画像。

建议名称：

```text
SkillInterviewAgent
```

或：

```text
TechStackInterviewAgent
```

### 9.1 工作方式

例如系统已经知道目标是 AI Agent 工程师，需要：

```text
Python
LLM API
LangGraph
RAG
Tool Calling
State Management
Vector DB
```

不要一次性让用户回答全部技能，而应该围绕已有证据逐步追问。

例如：

```text
Agent：
你平时主要用 Python 做什么类型的项目？有没有独立完成过完整项目？
```

用户：

```text
我写过几个 Flask 项目，也写过爬虫。
```

系统形成证据：

```text
Python
estimated_level ≈ 3
confidence ≈ 0.85
```

然后继续：

```text
Agent：
你之前有调用过 OpenAI、DeepSeek 这类大模型 API 吗？
```

用户：

```text
有，我用 DeepSeek API 做过聊天机器人。
```

系统形成：

```text
LLM API
estimated_level ≈ 3
```

继续：

```text
Agent：
你的聊天机器人有没有让模型自动决定调用函数或者工具？
```

用户：

```text
有，用过 Tool Calling。
```

得到：

```text
Tool Calling
estimated_level ≈ 3
```

这种模式比简单问卷式调查更自然。

---

## 10. UserSkill 数据结构

用户技能信息应统一为结构化数据。

```python
class UserSkill(BaseModel):
    skill_id: str
    skill_name: str
    level: int | None = None
    confidence: float = 0.0
    evidence: list[str] = []
    source: str = "conversation"
    last_updated: datetime | None = None
```

用户完整画像：

```python
class UserSkillProfile(BaseModel):
    user_id: str
    skills: list[UserSkill]
    last_updated: datetime
```

示例：

```json
{
  "user_id": "user_001",
  "skills": [
    {
      "skill_name": "Python",
      "level": 3,
      "confidence": 0.91,
      "evidence": [
        "Flask 项目",
        "爬虫项目",
        "独立开发"
      ]
    },
    {
      "skill_name": "LLM API",
      "level": 3,
      "confidence": 0.82,
      "evidence": [
        "DeepSeek API 聊天机器人"
      ]
    },
    {
      "skill_name": "Tool Calling",
      "level": 2,
      "confidence": 0.65,
      "evidence": [
        "使用过 Tool Calling"
      ]
    }
  ]
}
```

---

## 11. 不建议让 LLM 直接决定技能等级

不要采用：

```text
用户回答
  ↓
LLM
  ↓
Python = 3
```

更合理的是：

```text
用户回答
   ↓
Evidence Extractor
   ↓
Skill Evidence
   ↓
Skill Level Estimator
   ↓
UserSkill
```

技能等级最好由“行为证据”驱动。

例如：

| 用户证据 | 可以得到的结论 |
|---|---|
| 只听说过 Python | 了解级 |
| 能写简单脚本 | 基础使用 |
| 有 Flask 项目 | 熟练度提升 |
| 能独立设计项目架构 | 高熟练度 |
| 能优化复杂系统并沉淀方法论 | 高阶 |

第一版不必过度复杂，但应该保留：

```text
level
confidence
evidence
```

这三个核心字段。

---

## 12. Gap Engine

当系统同时拥有：

```text
TargetSkillProfile
```

和：

```text
UserSkillProfile
```

之后，缺口分析主要是确定性计算，不应主要依赖 Agent。

例如目标：

```text
Python      4
LangGraph   4
RAG         3
ToolCalling 4
```

用户当前：

```text
Python      3
LangGraph   1
RAG         2
ToolCalling 3
```

则：

```text
Python      gap = 1
LangGraph   gap = 3
RAG         gap = 1
ToolCalling gap = 1
```

### 12.1 SkillGap

建议：

```python
class SkillGap(BaseModel):
    skill_id: str
    skill_name: str
    current_level: int | None
    target_level: int
    gap: int
    priority: float
    reasons: list[str] = []
```

其中：

```text
priority
```

可综合：

- 目标要求权重
- 当前与目标等级差
- 技能是否属于前置技能
- 是否影响多个后续技能

---

## 13. 利用 Skill Graph 做真正的缺口分析

现有 `SkillPilot_skill_relations.json` 中已经提供：

```text
requires
composite_of
related
```

三个关系的意义：

### requires

表示学习或使用某技能必须具备的前置能力。

```text
LangGraph
   ↓ requires
LangChain
   ↓ requires
LLM API
   ↓ requires
Python
```

### composite_of

表示一个高级技能由多个子能力组成。

例如：

```text
LangGraph
├── State Management
├── Checkpoint
└── Node/Graph 编排
```

### related

表示关联技能，用于后续扩展建议，而不是核心前置关系。

---

## 14. 缺口分析示例

用户目标：

```text
AI Agent 工程师
```

目标技能：

```text
Python      4
LangGraph   4
LLM API     4
ToolCalling 4
RAG         3
```

用户当前：

```text
Python      4
LLM API     3
LangGraph   1
RAG         2
```

初步差距：

```text
LLM API       gap 1
LangGraph     gap 3
Tool Calling  gap 4
RAG           gap 1
```

进一步通过技能图谱：

```text
Tool Calling
     ↓ requires
LLM API
```

而：

```text
LangGraph
     ↓ requires
LangChain
     ↓ requires
LLM API
```

因此最终学习顺序应优先考虑：

```text
LLM API
   ↓
LangChain
   ↓
LangGraph
   ↓
Tool Calling
   ↓
RAG
```

实际顺序还应结合技能权重、用户当前能力和岗位要求进一步计算。

---

## 15. Agent 与 Engine 必须分离

这是整个系统架构最重要的边界之一。

### Agent 负责

```text
自然语言理解
上下文理解
对话
追问
决策
调用工具
```

### Engine 负责

```text
技能查询
技能图谱遍历
岗位匹配
技能差距计算
技能排序
学习路径计算
```

例如：

```text
SkillInterviewAgent
        │
        ▼
SkillProfileEngine
```

而不是：

```text
SkillInterviewAgent
        │
        └── 自己完成所有技能计算
```

这样可以保证逻辑可测试、可重复，也更容易后期替换模型。

---

## 16. 推荐代码目录

当前项目可以逐步向下面的结构演进：

```text
app/
│
├── agents/
│   ├── router_agent.py
│   ├── chat_agent.py
│   │
│   ├── tech/
│   │   ├── requirement_agent.py
│   │   └── requirement_parser.py
│   │
│   ├── job/
│   │   ├── requirement_agent.py
│   │   └── requirement_parser.py
│   │
│   ├── interview/
│   │   ├── skill_interview_agent.py
│   │   ├── question_generator.py
│   │   └── evidence_extractor.py
│   │
│   └── planning/
│       └── learning_plan_agent.py
│
├── domain/
│   ├── intent.py
│   ├── skill.py
│   ├── requirement.py
│   ├── profile.py
│   ├── gap.py
│   └── role.py
│
├── engines/
│   ├── skill_engine.py
│   ├── graph_engine.py
│   ├── gap_engine.py
│   ├── role_engine.py
│   └── recommendation_engine.py
│
├── knowledge/
│   ├── skill_repository.py
│   ├── role_repository.py
│   └── resource_repository.py
│
├── orchestrator/
│   ├── graph.py
│   └── state.py
│
└── persistence/
```

---

## 17. LangGraph State 设计

当前 State 已经不足以支撑新的多 Agent 流程。

建议至少包括：

```python
class SkillPilotState(TypedDict):
    # 对话
    messages: list

    # 用户当前意图
    intent: IntentType | None

    # 用户原始目标
    user_goal: str | None

    # 目标技能画像
    target_profile: TargetProfile | None

    # 用户技能画像
    user_profile: UserSkillProfile | None

    # 当前访谈状态
    interview_state: InterviewState | None

    # 技能缺口
    skill_gaps: list[SkillGap]

    # 当前 Agent
    current_agent: str

    # 工作流状态
    workflow_status: str
```

其中 `messages` 可以继续使用 Checkpointer 持久化多轮上下文。

---

## 18. 完整业务闭环

最终系统形成以下闭环：

```text
              用户自然语言
                    │
                    ▼
              Intent Router
                    │
          ┌─────────┴─────────┐
          ▼                   ▼
      技术目标              岗位目标
          │                   │
          ▼                   ▼
   Tech Requirement       Job Requirement
          │                   │
          └─────────┬─────────┘
                    ▼
             Target Profile
                    │
                    ▼
            Skill Interview
                    │
                    ▼
             User Profile
                    │
                    ▼
              Gap Engine
                    │
                    ▼
              Skill Graph
                    │
                    ▼
           ┌────────┴────────┐
           ▼                 ▼
       缺口技能          已掌握技能
           │
           ▼
      Learning Plan
           │
           ▼
          学习
           │
           ▼
       再次访谈/更新
           │
           └──────────────→ User Profile
```

---

## 19. 三份核心知识库的重新定位

当前仓库中的三个 JSON 文件可以直接承担新系统知识层的核心职责。

| 文件 | 新架构中的作用 |
|---|---|
| `SkillPilot_role_competencies.json` | 岗位能力知识库 |
| `SkillPilot_skill_relations.json` | 技能关系知识库 |
| `SkillPilot_knowledge_sources.json` | 学习资源知识库 |

### SkillPilot_role_competencies.json

用于：

```text
岗位
→ required_skills
→ required_level
→ weight
```

### SkillPilot_skill_relations.json

用于：

```text
技能
→ requires
→ composite_of
→ related
```

### SkillPilot_knowledge_sources.json

用于：

```text
技能
→ 学习资料
→ 文档
→ 教程
→ 课程
→ 项目资源
```

---

## 20. 推荐的数据流

系统最终应该保证所有主要流程都能落到统一的数据对象。

```text
用户输入
   ↓
IntentResult
   ↓
TechRequirement / JobRequirement
   ↓
TargetProfile
   ↓
SkillInterview
   ↓
UserSkillProfile
   ↓
SkillGap
   ↓
LearningPlan / JobMatch
```

这套结构的核心优势在于：

1. 技术学习和岗位求职共享同一技能体系。
2. Agent 之间通过 Pydantic 数据契约传递数据。
3. 技能关系由知识库统一维护，不由不同 Agent 各自生成。
4. 缺口分析主要由确定性 Engine 完成，结果更稳定。
5. 后续可以继续扩展职位匹配、项目推荐、课程推荐、面试准备等功能，而不需要推翻核心结构。

---

## 21. 开发阶段划分

### 第一阶段：意图识别

只实现：

```text
User
 ↓
IntentRouter
 ↓
 ├── chat
 ├── tech_learning
 └── job_search
```

并首先固定：

```text
IntentResult
TechRequirement
JobRequirement
```

### 第二阶段：目标画像

实现：

```text
TargetProfile
```

把技术目标和岗位目标统一转换成技能要求。

### 第三阶段：技术栈访谈

实现：

```text
SkillInterviewAgent
       ↓
UserSkillProfile
```

同时实现：

```text
EvidenceExtractor
```

把用户回答转换成技能证据。

### 第四阶段：缺口分析

实现：

```text
GapEngine
```

结合：

```text
UserSkillProfile
TargetProfile
Skill Graph
```

计算真正的技能缺口与学习优先级。

### 第五阶段：学习规划与岗位匹配

实现：

```text
LearningPlanAgent
JobMatchEngine
RecommendationEngine
```

最终形成完整闭环。

---

## 22. 最终产品定位

SkillPilot 最终不应该只是一个：

> “帮我生成学习计划的 AI。”

而应该成为：

> **一个根据用户学习或求职目标建立目标技能模型，通过多轮对话建立个人技术栈画像，再利用技能关系图谱计算能力差距，并持续生成学习与职业成长路径的 Agent 系统。**

系统的真正核心不是 Agent 数量，而是下面三者之间的连接：

```text
        用户目标
           │
           ▼
     Target Skill Profile
           │
           │
           ▼
     User Skill Profile
           │
           ▼
        Skill Graph
           │
           ▼
        Skill Gaps
           │
           ▼
     Learning / Career Path
```

其中：

> **Agent 负责理解用户，Skill Graph 负责理解技能，Engine 负责计算结果，Pydantic Schema 负责连接整个系统。**

这应该成为 SkillPilot 后续架构设计的核心原则。
