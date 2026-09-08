"""Regression guard for internal delivery-milestone leakage in public runtime text."""
from __future__ import annotations

import ast
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
MILESTONE_RE = re.compile(r"\bM\d{1,3}\b", re.IGNORECASE)
PUBLIC_RUNTIME_FILES = (
    "src/rasai/m23_cli.py",
    "src/rasai/m25_cli.py",
    "src/rasai/m25_apdex_experience.py",
    "src/rasai/console_m23.py",
    "src/rasai/console_runtime.py",
)


def _static_text(node: ast.AST | None) -> str:
    if node is None:
        return ""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(_static_text(value) for value in node.values)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _static_text(node.left) + _static_text(node.right)
    return ""


def _call_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return ""


class PublicRuntimeLanguageTests(unittest.TestCase):
    def test_public_runtime_strings_do_not_expose_internal_milestones(self) -> None:
        violations: list[str] = []
        for relative in PUBLIC_RUNTIME_FILES:
            path = ROOT / relative
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    name = _call_name(node)
                    values: list[tuple[str, ast.AST]] = []
                    if name in {"print", "set_runtime_progress", "ValueError", "ArgumentTypeError"}:
                        values.extend((f"{name} argument", value) for value in node.args)
                        values.extend((f"{name} {kw.arg}", kw.value) for kw in node.keywords if kw.arg)
                    elif name == "add_argument":
                        values.extend(("add_argument help", kw.value) for kw in node.keywords if kw.arg == "help")

                    for context, value in values:
                        text = _static_text(value)
                        if text and MILESTONE_RE.search(text):
                            violations.append(f"{relative}:{getattr(node, 'lineno', '?')} {context}: {text!r}")

                    if name == "set_runtime_progress":
                        for keyword in node.keywords:
                            if keyword.arg == "detail" and isinstance(keyword.value, ast.Name) and keyword.value.id == "name":
                                violations.append(
                                    f"{relative}:{getattr(node, 'lineno', '?')} set_runtime_progress detail=name pode expor event ID interno"
                                )

                if isinstance(node, (ast.Assign, ast.AnnAssign)):
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    value = node.value
                    for target in targets:
                        if isinstance(target, ast.Attribute) and target.attr == "operation":
                            text = _static_text(value)
                            if text and MILESTONE_RE.search(text):
                                violations.append(
                                    f"{relative}:{getattr(node, 'lineno', '?')} operation pública: {text!r}"
                                )

        self.assertEqual([], violations, "\n".join(violations))


if __name__ == "__main__":
    unittest.main()
