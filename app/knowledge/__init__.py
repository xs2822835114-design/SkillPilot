"""知识层：全系统技能/岗位/学习资源的统一读写入口（方案第 19 节）。

设计原则：知识层独立存在，所有 Agent 统一访问本层，而不是各自维护技能知识。
- skill_repository：技能词典 + 技能关系（requires/composite_of/related）
- role_repository：岗位能力定义（role_competencies）
- resource_repository：学习资源（knowledge_sources）
"""
from app.knowledge.skill_repository import list_skills, relations, prerequisites, parent_skills, resolve_skill
from app.knowledge.role_repository import find_role, get_role, list_roles
from app.knowledge.resource_repository import resources_for

__all__ = [
    "list_skills",
    "relations",
    "prerequisites",
    "parent_skills",
    "resolve_skill",
    "list_roles",
    "get_role",
    "find_role",
    "resources_for",
]