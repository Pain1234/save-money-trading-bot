"""Static guard against holding transaction_scope across async waits."""

from __future__ import annotations

import ast
from pathlib import Path


def _is_transaction_scope(item: ast.withitem) -> bool:
    expression = item.context_expr
    return (
        isinstance(expression, ast.Call)
        and isinstance(expression.func, ast.Name)
        and expression.func.id == "transaction_scope"
    )


def test_transaction_scope_never_contains_await_boundary() -> None:
    services = Path(__file__).resolve().parents[2] / "services" / "paper_trading"
    violations: list[str] = []
    for path in services.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.With, ast.AsyncWith)):
                continue
            if not any(_is_transaction_scope(item) for item in node.items):
                continue
            if any(isinstance(child, ast.Await) for child in ast.walk(node)):
                violations.append(f"{path.name}:{node.lineno}")

    assert violations == []
