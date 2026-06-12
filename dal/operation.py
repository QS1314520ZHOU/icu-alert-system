"""
OperationDatabase — 统一执行层
================================

提供 query_list / query_one / count / insert / update / delete 六大方法，
入参为 ORM 模型类 + QueryCondition，业务代码与底层数据库完全解耦。

用法::

    from dal.operation import OperationDatabase as DB
    from dal.condition import QC

    # 查询列表
    patients = DB.query_list(
        Patient,
        QC().in_("saas_org_code", ["ORG001", "ORG002"]),
        order_by=["created_at desc"],
        page=1,
        size=20,
    )

    # 查询单条
    patient = DB.query_one(Patient, QC().eq("id", 42))

    # 计数
    total = DB.count(Patient, QC().eq("status", 1))

    # 新增
    DB.insert(patient_obj)      # 单条 ORM 实例
    DB.insert([p1, p2, p3])     # 批量

    # 更新（返回影响行数）
    DB.update(Patient, QC().eq("id", 42), {"status": 0})

    # 删除（返回影响行数）
    DB.delete(Patient, QC().eq("id", 42))
"""

from __future__ import annotations

from typing import Any, Sequence, Type, TypeVar

from sqlalchemy import select, func, delete, update as sa_update
from sqlalchemy.orm import DeclarativeBase, Session

from dal.condition import QC
from dal.config import get_session

T = TypeVar("T", bound=DeclarativeBase)


class OperationDatabase:
    """数据库操作门面（全静态方法，无需实例化）。"""

    # ── 查询 ──────────────────────────────────────────────────────

    @staticmethod
    def query_list(
        model_class: Type[T],
        condition: QC | None = None,
        *,
        order_by: list[str] | None = None,
        page: int | None = None,
        size: int | None = None,
        columns: list[str] | None = None,
    ) -> list[T] | list[Any]:
        """
        查询列表。

        Args:
            model_class: ORM 模型类
            condition: QueryCondition 条件（None = 无 WHERE）
            order_by: 排序字段列表，如 ["created_at desc", "id asc"]
            page: 页码（从 1 开始）
            size: 每页条数
            columns: 字段投影列表，如 ["id", "name"]；None = 全部字段

        Returns:
            模型实例列表（或 tuple 列表，当使用 columns 投影时）
        """
        session: Session = get_session()
        try:
            stmt = _build_select(model_class, condition, order_by, page, size, columns)
            result = session.execute(stmt)
            if columns:
                return list(result.all())
            return list(result.scalars().all())
        finally:
            session.close()

    @staticmethod
    def query_one(
        model_class: Type[T],
        condition: QC | None = None,
        *,
        columns: list[str] | None = None,
    ) -> T | Any | None:
        """
        查询单条记录。多条命中时取第一条；无结果返回 None。
        """
        session: Session = get_session()
        try:
            stmt = _build_select(model_class, condition, page=1, size=1, columns=columns)
            result = session.execute(stmt)
            if columns:
                row = result.first()
                return row if row else None
            return result.scalars().first()
        finally:
            session.close()

    @staticmethod
    def count(
        model_class: Type[T],
        condition: QC | None = None,
    ) -> int:
        """统计符合条件的记录数。"""
        session: Session = get_session()
        try:
            stmt = select(func.count()).select_from(model_class)
            if condition is not None:
                stmt = stmt.where(condition.build(model_class))
            return session.scalar(stmt) or 0
        finally:
            session.close()

    # ── 新增 ──────────────────────────────────────────────────────

    @staticmethod
    def insert(entity: T | Sequence[T]) -> None:
        """
        插入单条或批量记录。

        Args:
            entity: 单个 ORM 实例，或 ORM 实例列表
        """
        session: Session = get_session()
        try:
            if isinstance(entity, Sequence):
                session.add_all(entity)
            else:
                session.add(entity)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ── 更新 ──────────────────────────────────────────────────────

    @staticmethod
    def update(
        model_class: Type[T],
        condition: QC,
        values: dict[str, Any],
    ) -> int:
        """
        按条件批量更新字段。

        Args:
            model_class: ORM 模型类
            condition: 更新条件
            values: 要更新的 {字段名: 新值}

        Returns:
            影响行数
        """
        session: Session = get_session()
        try:
            stmt = (
                sa_update(model_class)
                .where(condition.build(model_class))
                .values(**values)
                .execution_options(synchronize_session="fetch")
            )
            result = session.execute(stmt)
            session.commit()
            return result.rowcount  # type: ignore[return-value]
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ── 删除 ──────────────────────────────────────────────────────

    @staticmethod
    def delete(
        model_class: Type[T],
        condition: QC,
    ) -> int:
        """
        按条件删除记录。

        Args:
            model_class: ORM 模型类
            condition: 删除条件

        Returns:
            影响行数
        """
        session: Session = get_session()
        try:
            stmt = (
                delete(model_class)
                .where(condition.build(model_class))
                .execution_options(synchronize_session="fetch")
            )
            result = session.execute(stmt)
            session.commit()
            return result.rowcount  # type: ignore[return-value]
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


# ── 内部辅助 ──────────────────────────────────────────────────────

def _build_select(
    model_class: Type[T],
    condition: QC | None = None,
    order_by: list[str] | None = None,
    page: int | None = None,
    size: int | None = None,
    columns: list[str] | None = None,
) -> select:
    """构建 SELECT 语句。"""
    # 投影 vs 全字段
    if columns:
        cols = [getattr(model_class, c) for c in columns]
        stmt = select(*cols).select_from(model_class)
    else:
        stmt = select(model_class)

    # WHERE
    if condition is not None:
        stmt = stmt.where(condition.build(model_class))

    # ORDER BY
    if order_by:
        table_cols = model_class.__table__.columns  # type: ignore[attr-defined]
        for item in order_by:
            parts = item.strip().split()
            col_name = parts[0]
            direction = parts[1].upper() if len(parts) > 1 else "ASC"
            col = table_cols[col_name]
            if direction == "DESC":
                stmt = stmt.order_by(col.desc())
            else:
                stmt = stmt.order_by(col.asc())

    # 分页
    if page is not None and size is not None:
        offset = (page - 1) * size
        stmt = stmt.offset(offset).limit(size)

    return stmt
