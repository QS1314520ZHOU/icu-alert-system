"""
ORM 模型定义
=============

提供 SQLAlchemy 2.0 声明式基类和示例 Patient 模型。
业务项目使用时，在自己的 models.py 中 import Base 并定义表。

字段命名说明：
    数据库字段用 snake_case（如 saas_org_code），对应 Java 中的驼峰命名。
    SQLAlchemy Column 名即 Python 属性名，查询时用 snake_case。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Integer,
    String,
    DateTime,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。"""
    pass


class Patient(Base):
    """
    示例模型：患者信息表。

    对应 Java 原型中的 Patient.class，包含 saasOrgCode、saasDepartmentCode 等字段。
    """
    __tablename__ = "patient"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, comment="主键ID"
    )
    saas_org_code: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="机构编码"
    )
    saas_department_code: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="科室编码"
    )
    name: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="患者姓名"
    )
    age: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="年龄"
    )
    gender: Mapped[str | None] = mapped_column(
        String(10), nullable=True, comment="性别"
    )
    status: Mapped[int] = mapped_column(
        Integer, default=1, comment="状态 1=有效 0=无效"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), comment="创建时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间"
    )

    def __repr__(self) -> str:
        return (
            f"<Patient(id={self.id}, name='{self.name}', "
            f"org='{self.saas_org_code}', dept='{self.saas_department_code}')>"
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "saas_org_code": self.saas_org_code,
            "saas_department_code": self.saas_department_code,
            "name": self.name,
            "age": self.age,
            "gender": self.gender,
            "status": self.status,
            "created_at": str(self.created_at) if self.created_at else None,
            "updated_at": str(self.updated_at) if self.updated_at else None,
        }
