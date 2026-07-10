"""
QueryCondition 链式构造器 (QueryCondition / QC)
================================================

将 Java 风格的链式查询条件翻译为 SQLAlchemy WHERE 表达式。
所有方法返回 self，支持无限链式调用。

用法::

    cond = (
        QC()
        .in_("saas_org_code", ["ORG001", "ORG002"])
        .in_("saas_department_code", ["DEPT_A", "DEPT_B"])
        .eq("status", 1)
    )
    rows = OperationDatabase.query_list(Patient, cond)

复杂条件::

    cond = (
        QC()
        .or_(
            QC().like("name", "%张%"),
            QC().like("name", "%李%"),
        )
        .gte("age", 18)
    )
"""

from __future__ import annotations

from typing import Any, Callable, Sequence

from sqlalchemy import Column, and_, or_, ColumnElement, literal
from sqlalchemy.orm import DeclarativeBase


class QC:
    """
    QueryCondition — 链式查询条件构造器。

    内部维护一个 (column_name, op_func, value) 列表，
    build() 时通过 SQLAlchemy mapper 反射出 Column 对象并生成 WHERE 子句。
    """

    def __init__(self) -> None:
        # 每条记录: (column_name: str, op: str, value: Any)
        self._clauses: list[tuple[str, str, Any]] = []
        # 复合条件（or_ / and_ 嵌套的子 QC）
        self._groups: list[tuple[str, list[QC]]] = []

    # ── 基础比较 ──────────────────────────────────────────────────

    def eq(self, column: str, value: Any) -> "QC":
        """column = value"""
        self._clauses.append((column, "eq", value))
        return self

    def ne(self, column: str, value: Any) -> "QC":
        """column != value"""
        self._clauses.append((column, "ne", value))
        return self

    def gt(self, column: str, value: Any) -> "QC":
        """column > value"""
        self._clauses.append((column, "gt", value))
        return self

    def gte(self, column: str, value: Any) -> "QC":
        """column >= value"""
        self._clauses.append((column, "gte", value))
        return self

    def lt(self, column: str, value: Any) -> "QC":
        """column < value"""
        self._clauses.append((column, "lt", value))
        return self

    def lte(self, column: str, value: Any) -> "QC":
        """column <= value"""
        self._clauses.append((column, "lte", value))
        return self

    def like(self, column: str, pattern: str) -> "QC":
        """column LIKE pattern"""
        self._clauses.append((column, "like", pattern))
        return self

    def between(self, column: str, low: Any, high: Any) -> "QC":
        """low <= column <= high"""
        self._clauses.append((column, "between", (low, high)))
        return self

    def is_null(self, column: str, nullable: bool = True) -> "QC":
        """column IS [NOT] NULL"""
        self._clauses.append((column, "is_null", nullable))
        return self

    # ── 集合操作 ──────────────────────────────────────────────────

    def in_(self, column: str, values: Sequence[Any]) -> "QC":
        """column IN (values...)"""
        self._clauses.append((column, "in_", list(values)))
        return self

    def nin(self, column: str, values: Sequence[Any]) -> "QC":
        """column NOT IN (values...)"""
        self._clauses.append((column, "nin", list(values)))
        return self

    # ── 复合条件 ──────────────────────────────────────────────────

    def or_(self, *conditions: "QC") -> "QC":
        """OR 组合多个子条件::

            QC().or_(QC().eq("a", 1), QC().eq("b", 2))
        """
        self._groups.append(("or", list(conditions)))
        return self

    def and_(self, *conditions: "QC") -> "QC":
        """AND 组合多个子条件（默认行为，但显式嵌套时有用）。"""
        self._groups.append(("and", list(conditions)))
        return self

    # ── 构建 SQLAlchemy WHERE 表达式 ──────────────────────────────

    def build(self, model_class: type[DeclarativeBase]) -> ColumnElement[bool]:
        """
        将本条件翻译为 SQLAlchemy WHERE 子句。

        Args:
            model_class: SQLAlchemy ORM 模型类

        Returns:
            可直接传给 .where() 的 SQLAlchemy 表达式
        """
        table_cols = model_class.__table__.columns  # type: ignore[attr-defined]
        parts: list[ColumnElement] = []

        # 基础列条件
        for col_name, op, value in self._clauses:
            col: Column = table_cols[col_name]
            expr = self._op_to_expr(col, op, value)
            parts.append(expr)

        # 复合嵌套条件
        for logic, sub_conditions in self._groups:
            sub_exprs = [sc.build(model_class) for sc in sub_conditions]
            if logic == "or":
                parts.append(or_(*sub_exprs))
            else:
                parts.append(and_(*sub_exprs))

        if not parts:
            # 空条件 → 返回恒真
            return literal(True)

        return and_(*parts)

    @staticmethod
    def _op_to_expr(col: Column, op: str, value: Any) -> ColumnElement:
        """将单个操作翻译为 SQLAlchemy 表达式。"""
        _OPS: dict[str, Callable[[Column, Any], ColumnElement]] = {
            "eq": lambda c, v: c == v,
            "ne": lambda c, v: c != v,
            "gt": lambda c, v: c > v,
            "gte": lambda c, v: c >= v,
            "lt": lambda c, v: c < v,
            "lte": lambda c, v: c <= v,
            "like": lambda c, v: c.like(v),
            "between": lambda c, v: c.between(v[0], v[1]),
            "is_null": lambda c, v: c.is_(None) if v else c.isnot(None),
            "in_": lambda c, v: c.in_(v),
            "nin": lambda c, v: ~c.in_(v),
        }
        fn = _OPS.get(op)
        if fn is None:
            raise ValueError(f"不支持的操作: {op}")
        return fn(col, value)

    def __repr__(self) -> str:
        clauses_repr = [
            f"{col} {op} {val!r}" for col, op, val in self._clauses
        ]
        groups_repr = [
            f"{logic}({', '.join(repr(sc) for sc in subs)})"
            for logic, subs in self._groups
        ]
        return f"QC({' AND '.join(clauses_repr + groups_repr)})"


# 快捷别名
QueryCondition = QC
