"""
dal — 统一数据访问层 (Unified Data Access Layer)
=================================================

数据库无关的 DAL 模块。基于 SQLAlchemy 2.0，通过「数据库注册表」切换后端，
业务代码零修改。

用法::

    from dal.config import configure
    from dal.operation import OperationDatabase
    from dal.condition import QC

    configure("postgresql")          # 或 "kingbase", "mysql" …
    rows = OperationDatabase.query_list(Patient, QC().in_("saas_org_code", ["A","B"]))
"""

from dal.config import configure, get_session_factory, DB_REGISTRY
from dal.condition import QC
from dal.operation import OperationDatabase

__all__ = [
    "configure",
    "get_session_factory",
    "DB_REGISTRY",
    "QC",
    "OperationDatabase",
]
