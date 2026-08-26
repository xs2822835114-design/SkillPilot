"""Agent 基类：固定输入/输出契约。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.orchestrator.state import SkillMapState


class BaseAgent(ABC):
    """所有业务 Agent 的基类。

    约定：
    - 输入：SkillMapState（结构化状态快照）
    - 输出：结构化 JSON（dict），由 Pydantic/Structured Output 校验
    - Agent 不感知 HTTP、不做持久化（职责边界见阶段 1 计划书第 4 节）
    """

    name: str = "base"

    @abstractmethod
    def invoke(self, state: SkillMapState) -> dict[str, Any]:
        """处理状态，返回需要合并回 State 的字段。"""
        raise NotImplementedError
