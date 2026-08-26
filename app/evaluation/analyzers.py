"""Python 静态分析（阶段 6，evaluation/analyzers）→ 结构化 CheckResult。

标准库 compile + ast 保证语法/结构/可运行性/测试存在性检查；lint 级（未使用
导入/TODO）依赖 pyflakes，缺失时降级为启发式，始终不抛错。
"""
from __future__ import annotations

import ast
import logging
from typing import Any

logger = logging.getLogger(__name__)


def analyze(code_files: dict[str, str], strict: bool = True) -> list[dict[str, Any]]:
    """对 `{filename: content}` 做静态分析，返回结构化检查结果列表。

    每项：{"type","passed","message"}。type ∈ syntax/structure/runnable/tests/lint。
    """
    if not code_files:
        return [{"type": "empty", "passed": False, "message": "未收到任何代码文件"}]

    checks = [{"type": "syntax", "passed": False, "message": ""}]
    main_file, main_src = _pick_main(code_files)

    # 1) 语法
    try:
        compile(main_src, main_file, "exec")
        checks[0]["passed"] = True
        checks[0]["message"] = f"「{main_file}」可编译"
    except SyntaxError as exc:
        checks[0]["message"] = f"语法错误：{exc}"
        _append(checks, "structure", True, "（因语法失败跳过）")
        _append(checks, "runnable", False, "语法错误无法运行")
        _append(checks, "tests", False, "语法错误，无法抽取测试")
        return checks

    # 2) 结构
    tree = ast.parse(main_src)
    n_fn = sum(1 for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)))
    n_cls = sum(1 for n in ast.walk(tree) if isinstance(n, ast.ClassDef))
    has_structure = n_fn > 0 or n_cls > 0
    _append(
        checks, "structure", has_structure,
        f"存在 {n_fn} 个函数、{n_cls} 个类" if has_structure else "未发现函数或类定义",
    )

    # 3) 可运行入口
    runnable = _has_main(tree) or _has_top_level_exec(main_src)
    _append(checks, "runnable", runnable,
            "存在 __main__ 入口或顶层可执行调用" if runnable else "未发现可执行的入口/顶层调用")

    # 4) 测试存在性
    tests = _count_tests(code_files)
    _append(checks, "tests", tests > 0,
            f"发现测试用例 {tests} 个" if tests else "未发现测试用例")

    # 5) lint（pyflakes 优先，缺失降级启发式）
    if strict:
        _append_lint(checks, main_src)

    return checks


def _append(checks: list[dict], typ: str, passed: bool, message: str) -> None:
    checks.append({"type": typ, "passed": bool(passed), "message": message})


def _pick_main(code_files: dict[str, str]) -> tuple[str, str]:
    if "main.py" in code_files:
        return "main.py", code_files["main.py"]
    # 体积最大的 .py，排除测试
    cands = [f for f in code_files if f.endswith(".py") and not f.startswith("test")]
    if not cands:
        cands = [f for f in code_files if f.endswith(".py")]
    if not cands:
        return next(iter(code_files)), next(iter(code_files.values()))
    f = max(cands, key=lambda x: len(code_files[x]))
    return f, code_files[f]


def _has_main(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            test = node.test
            if (
                isinstance(test, ast.Compare)
                and isinstance(test.left, ast.Name)
                and test.left.id == "__name__"
            ):
                return True
    return False


def _has_top_level_exec(src: str) -> bool:
    # 排除 def/class 与 import，检测顶层函数调用（如 search(...)、demo()）
    tree = ast.parse(src)
    last = [n for n in tree.body if isinstance(n, ast.Expr)]
    return any(isinstance(n.value, ast.Call) for n in last)


def _count_tests(code_files: dict[str, str]) -> int:
    n = 0
    for fname, src in code_files.items():
        if fname.startswith("test") or "test_" in fname:
            n += 1
        n += sum(1 for _ in _find_test_defs(src))
    return n


def _find_test_defs(src: str):
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
            yield node


def _append_lint(checks: list[dict], src: str) -> None:
    issues: list[str] = []
    try:
        import pyflakes  # noqa: F401

        issues = _pyflakes_issues(src)
    except Exception:  # noqa: BLE001
        issues = _heuristic_lint(src)  # 无 pyflakes 时启发式
    if issues:
        _append(checks, "lint", False, "；".join(issues[:3]))
    else:
        _append(checks, "lint", True, "未发现明显代码质量问题")


def _pyflakes_issues(src: str) -> list[str]:
    from pyflakes.api import checkSourceString
    from pyflakes.reporter import Reporter

    collected: list[str] = []

    class _Reporter(Reporter):
        def unexpectedError(self, filename, msg):  # noqa: N802
            pass

        def syntaxError(self, filename, msg, lineno, column, source):  # noqa: N802
            pass

        def flake(self, message):  # noqa: N802
            collected.append(str(message))

    checkSourceString(src, filename="code.py", reporter=_Reporter())
    return collected


def _heuristic_lint(src: str) -> list[str]:
    issues: list[str] = []
    if any(line.strip().startswith("import ") or line.strip().startswith("from ")
           for line in src.splitlines()):
        # 粗略：以存在若干 import 但不推断是否复用为基准，仅提示 TODO/FIXME
        pass  # 不误报未使用，交由 pyflakes 或人工
    todo = [ln.strip() for ln in src.splitlines() if any(k in ln for k in ("TODO", "FIXME", "XXX"))]
    if todo:
        issues.append("存在 TODO/FIXME 注释")
    return issues