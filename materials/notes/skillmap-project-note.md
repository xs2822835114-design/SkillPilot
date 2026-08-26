# SkillMap 项目简介

SkillMap 是一个个人技术栈成长与能力规划智能体，帮助工程师梳理目标岗位要求、评估当前能力差距，并制定可执行的学习路径。

## 核心能力

- 对话式交互：与用户用自然语言沟通，理解其背景与目标。
- Agent 编排：基于 LangGraph 构建多步 Agent 流程，管理会话状态与上下文。
- 会话持久化：通过 PostgreSQL + PostgresSaver 保存对话 Checkpoint，支持跨重启恢复上下文。
- RAG 知识库：将技术资料切块、向量化后落库，检索增强问答并给出证据来源。

## 技术栈

- 后端：Python 3.12 / Flask / LangGraph / LangChain
- 数据库：PostgreSQL 16 + pgvector
- 前端：Vue 3 + Vite + Pinia
- 模型：DeepSeek（对话）/ Qwen-DashScope（Embedding，可选）

## 工程分层

采用单向依赖：API 层 → 编排/知识层 → 持久化层，模块职责解耦、契约先行，便于后续扩展新 Agent。