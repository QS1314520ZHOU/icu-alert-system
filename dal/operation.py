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

    # 查询单条（建议指定 order_by 确保结果稳定）
    patient = DB.query_one(Patient, QC().eq("id", 42), order_by=["id"])

    # 计数
    total = DB.count(Patient, QC().eq("status", 1))

    # 新增
    DB.insert(patient_obj)      # 单条 ORM 实例
    DB.insert([p1, p2, p3])     # 批量

    # 更新（返回影响行数）
    DB.update(Patient, QC().eq("id", 42), {"status": 0})

    # 删除（返回影响行数）
    DB.delete(Patient, QC().eq("id", 42))

    # 事务组合（多个操作在同一事务中）
    with DB.transaction() as session:
        session.add(p1)
        session.execute(sa_update(Patient).where(...).values(...))
        # 退出 with 时自动 commit，异常时自动 rollback
"""

from __future__ import annotations

import re
from contextlib import contextmanager
from typing import Any, Type, TypeVar

from sqlalchemy import select, func, delete, update as sa_update
from sqlalchemy.orm import DeclarativeBase, Session

from dal.condition import QC
from dal.config import get_session

T = TypeVar("T", bound=DeclarativeBase)

# order_by 解析正则：字段名 + 可选的 ASC/DESC + 可选的 NULLS FIRST/LAST
# 支持格式：
#   - "age"
#   - "age desc"
#   - "age DESC NULLS LAST"
#   - "t.age"（带表名前缀）
#   - '"MyColumn"'（带引号的标识符，金仓/PG 大小写敏感场景）
#   - "age DESC NULLS LAST"
_ORDER_BY_RE = re.compile(
    r'^(?:"([^"]+)"|([\w.]+))\s*(?:(ASC|DESC)\s*(?:NULLS\s+(FIRST|LAST))?)?$',
    re.IGNORECASE,
)


class OperationDatabase:
    """数据库操作门面（全静态方法，无需实例化）。"""

    # ── 事务支持 ──────────────────────────────────────────────────

    @staticmethod
    @contextmanager
    def transaction():
        """
        事务上下文管理器，用于在同一事务中组合多个操作。

        **重要警告：事务块内请使用 yield 出来的 session 直接操作，
        不要再调用 DB.query_list / DB.update / DB.delete 等静态方法，
        因为它们会另开 session、独立提交，不在当前事务中。**

        错误示例::

            with DB.transaction() as session:
                session.add(p1)
                DB.update(Patient, QC().eq("id", 1), {"status": 0})  # ← 另一个 session！
                # 如果 p1 插入失败回滚，update 已经提交了，数据不一致！

        正确示例::

            with DB.transaction() as session:
                session.add(p1)
                session.execute(
                    sa_update(Patient).where(Patient.id == 1).values(status=0)
                )
                # 全部在同一事务中，要么全成功，要么全回滚

        用法::

            with DB.transaction() as session:
                session.add(p1)
                session.execute(sa_update(Patient).where(...).values(...))
                # 退出 with 时自动 commit，异常时自动 rollback

        Yields:
            Session: 数据库会话对象，用于在同一事务中执行多个操作
        """
        session: Session = get_session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

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
            order_by: 排序字段列表，如 ["created_at desc", "id asc", "name NULLS LAST"]
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
        order_by: list[str] | None = None,
        columns: list[str] | None = None,
    ) -> T | Any | None:
        """
        查询单条记录。多条命中时取第一条；无结果返回 None。

        注意：不指定 order_by 时，"第一条"的顺序不保证稳定。
        建议总是传入 order_by 确保结果确定性，如 order_by=["id"]。

        Args:
            model_class: ORM 模型类
            condition: QueryCondition 条件
            order_by: 排序字段列表（强烈建议指定，确保结果确定性）
            columns: 字段投影列表

        Returns:
            模型实例、tuple 或 None
        """
        session: Session = get_session()
        try:
            stmt = _build_select(
                model_class, condition, order_by=order_by, page=1, size=1, columns=columns
            )
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
    def insert(entity: T | list[T] | tuple[T, ...]) -> None:
        """
        插入单条或批量记录。

        Args:
            entity: 单个 ORM 实例，或 list/tuple 包含的 ORM 实例列表

        Raises:
            TypeError: 如果传入非 ORM 实例或非 list/tuple 容器
        """
        session: Session = get_session()
        try:
            # 修复 BUG: isinstance(entity, Sequence) 会误判 str 等类型
            # 直接用 (list, tuple) 判断最稳
            if isinstance(entity, (list, tuple)):
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
            # 修复 BUG: synchronize_session="fetch" 在金仓/达梦等非标准库上可能出问题
            # 且会多一次 SELECT 查询影响性能。这里更新后直接返回 rowcount，
            # 不需要同步 session 中的对象，用 False 最稳。
            stmt = (
                sa_update(model_class)
                .where(condition.build(model_class))
                .values(**values)
                .execution_options(synchronize_session=False)
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
            # 同 update，用 synchronize_session=False
            stmt = (
                delete(model_class)
                .where(condition.build(model_class))
                .execution_options(synchronize_session=False)
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

def _parse_order_by_item(item: str, table_cols) -> Any:
    """
    解析单个 order_by 字符串，返回 SQLAlchemy ColumnElement。

    支持格式:
        - "age"
        - "age desc"
        - "age DESC NULLS LAST"
        - "created_at ASC NULLS FIRST"
        - "t.age"（带表名前缀，会取最后一段）
        - '"MyColumn"'（带引号的标识符，金仓/PG 大小写敏感场景）

    Args:
        item: 排序描述字符串
        table_cols: SQLAlchemy Table.columns 对象

    Returns:
        排序表达式

    Raises:
        ValueError: 格式不合法时
    """
    match = _ORDER_BY_RE.match(item.strip())
    if not match:
        raise ValueError(
            f"无法解析 order_by 项: {item!r}。"
            f"支持格式: 'field', 'field asc', 'field DESC NULLS LAST', "
            f'"quoted_field", "t.field"'
        )

    # 两个捕获组：group(1)=带引号的列名, group(2)=不带引号的列名
    col_name = match.group(1) or match.group(2)
    direction = (match.group(3) or "ASC").upper()
    nulls = match.group(4)  # "FIRST" / "LAST" / None

    # 处理 "t.age" 这种带表名前缀的情况，取最后一段作为列名
    if "." in col_name:
        col_name = col_name.rsplit(".", 1)[-1]

    # 从 table_cols 取列
    if col_name not in table_cols:
        raise ValueError(
            f"order_by 列名 {col_name!r} 在模型中不存在。"
            f"可用列: {list(table_cols.keys())}"
        )
    col = table_cols[col_name]

    # 构建排序表达式
    if direction == "DESC":
        expr = col.desc()
    else:
        expr = col.asc()

    # NULLS FIRST/LAST（PG/金仓支持，MySQL 忽略）
    if nulls:
        from sqlalchemy import nulls_first, nulls_last
        if nulls.upper() == "FIRST":
            expr = nulls_first(expr)
        else:
            expr = nulls_last(expr)

    return expr


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
            expr = _parse_order_by_item(item, table_cols)
            stmt = stmt.order_by(expr)

    # 分页
    if page is not None and size is not None:
        offset = (page - 1) * size
        stmt = stmt.offset(offset).limit(size)

    return stmt
