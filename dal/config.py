"""
数据库注册表 + 连接配置
========================

设计目标：
- 新增数据库只需在 DB_REGISTRY 添加一条配置。
- 连接 URL 优先读环境变量 DAL_DATABASE_URL，否则按注册表模板拼接。
- 切库不改业务代码，只改环境变量或 configure("name") 调用。

环境变量优先级：
    DAL_DATABASE_URL > DAL_DB_NAME > 注册表默认

注册表字段说明：
    dialect   : SQLAlchemy 方言名（engine URL 的 scheme 部分）
    driver    : DBAPI 驱动名（拼在 dialect+driver://）
    url_tpl   : URL 模板，{user}/{password}/{host}/{port}/{db} 会被替换
    default_* : 当环境变量缺失时的默认值
    note      : 兼容等级 / 备注

兼容性扩展指南：
    - PostgreSQL  → 已实现
    - KingbaseES  → 已配置（PG 兼容模式，端口 54321，psycopg 驱动）
    - MySQL/MariaDB → dialect="mysql", driver="pymysql"
    - 达梦 DM     → dialect="dm", driver="dmPython"（需 pip install dmPython 或厂商包）
    - OpenGauss   → dialect="postgresql", driver="psycopg2"（PG 兼容）
    - TiDB        → dialect="mysql", driver="pymysql"（MySQL 兼容）
    - 人大金仓 Oracle 兼容模式 → dialect="oracle", driver="cx_Oracle" 或厂商驱动
"""

from __future__ import annotations

import os
from typing import Any

from sqlalchemy import create_engine, Engine
from sqlalchemy.orm import sessionmaker, Session

# ── 数据库注册表 ──────────────────────────────────────────────────
DB_REGISTRY: dict[str, dict[str, Any]] = {
    # ─── PostgreSQL（本地开发）── 已验证可跑 ───
    "postgresql": {
        "dialect": "postgresql",
        "driver": "psycopg2",
        "url_tpl": "postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}",
        "default_host": "localhost",
        "default_port": 5432,
        "default_db": "postgres",
        "default_user": "postgres",
        "default_password": "123456",
        "note": "[OK] 已验证可跑",
    },
    # ─── 人大金仓 KingbaseES（PG 兼容模式）── 配置就绪待真机验证 ───
    "kingbase": {
        "dialect": "postgresql",       # 金仓 PG 兼容模式复用 PG dialect
        "driver": "psycopg2",          # 金仓自带 psycopg2 兼容驱动
        "url_tpl": "postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}",
        "default_host": "localhost",
        "default_port": 54321,         # 金仓默认端口
        "default_db": "test",
        "default_user": "system",
        "default_password": "123456",
        "note": "[待验证] 配置就绪，待真机验证。需注意：端口54321、标识符大小写、"
                "PG兼容模式 vs Oracle兼容模式差异",
    },
    # ─── MySQL / MariaDB ── 待扩展 ───
    "mysql": {
        "dialect": "mysql",
        "driver": "pymysql",
        "url_tpl": "mysql+pymysql://{user}:{password}@{host}:{port}/{db}?charset=utf8mb4",
        "default_host": "localhost",
        "default_port": 3306,
        "default_db": "test",
        "default_user": "root",
        "default_password": "",
        "note": "[待扩展] 需 pip install pymysql",
    },
    # ─── 达梦 DM ── 待扩展 ───
    "dameng": {
        "dialect": "dm",               # 达梦需要厂商方言 dmPython
        "driver": "dmPython",
        "url_tpl": "dm+dmPython://{user}:{password}@{host}:{port}",
        "default_host": "localhost",
        "default_port": 5236,
        "default_db": "",
        "default_user": "SYSDBA",
        "default_password": "SYSDBA",
        "note": "[待扩展] 需 pip install dmPython 或厂商驱动包",
    },
    # ─── OpenGauss ── 待扩展 ───
    "opengauss": {
        "dialect": "postgresql",
        "driver": "psycopg2",
        "url_tpl": "postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}",
        "default_host": "localhost",
        "default_port": 5432,
        "default_db": "test",
        "default_user": "gaussdb",
        "default_password": "",
        "note": "[待扩展] OpenGauss 兼容 PG 协议，直接复用 PG dialect",
    },
    # ─── TiDB ── 待扩展 ───
    "tidb": {
        "dialect": "mysql",
        "driver": "pymysql",
        "url_tpl": "mysql+pymysql://{user}:{password}@{host}:{port}/{db}?charset=utf8mb4",
        "default_host": "localhost",
        "default_port": 4000,
        "default_db": "test",
        "default_user": "root",
        "default_password": "",
        "note": "[待扩展] TiDB 兼容 MySQL 协议",
    },
}

# ── 运行时状态 ────────────────────────────────────────────────────
_current_db_name: str = "postgresql"
_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def _build_url(name: str) -> str:
    """
    优先从环境变量 DAL_DATABASE_URL 读取完整 URL；
    否则按注册表模板 + 环境变量/默认值拼接。
    """
    # 1. 完整 URL 环境变量（最高优先）
    env_url = os.environ.get("DAL_DATABASE_URL")
    if env_url:
        return env_url

    entry = DB_REGISTRY[name]

    def _env(key: str, default: str) -> str:
        """DAL_{KEY} 环境变量 → 注册表默认值"""
        env_key = f"DAL_{key.upper()}"
        return os.environ.get(env_key, default)

    return entry["url_tpl"].format(
        user=_env("user", entry["default_user"]),
        password=_env("password", entry["default_password"]),
        host=_env("host", entry["default_host"]),
        port=_env("port", str(entry["default_port"])),
        db=_env("db", entry["default_db"]),
    )


def configure(
    db_name: str = "postgresql",
    *,
    echo: bool = False,
    pool_size: int = 5,
    max_overflow: int = 10,
    **engine_kwargs: Any,
) -> Engine:
    """
    初始化全局引擎和会话工厂。

    Args:
        db_name: 注册表中的数据库名（如 "postgresql", "kingbase"）
        echo: 是否打印 SQL（调试用）
        pool_size: 连接池大小
        max_overflow: 溢出连接数
        **engine_kwargs: 其他传给 create_engine 的参数

    Returns:
        创建好的 Engine 实例
    """
    global _current_db_name, _engine, _session_factory

    if db_name not in DB_REGISTRY:
        raise ValueError(
            f"未知数据库 '{db_name}'，可选: {list(DB_REGISTRY.keys())}"
        )

    _current_db_name = db_name
    url = _build_url(db_name)

    _engine = create_engine(
        url,
        echo=echo,
        pool_size=pool_size,
        max_overflow=max_overflow,
        **engine_kwargs,
    )
    _session_factory = sessionmaker(bind=_engine, expire_on_commit=False)

    entry = DB_REGISTRY[db_name]
    print(f"[DAL] 已配置数据库: {db_name} ({entry['dialect']}+{entry['driver']})")
    print(f"[DAL] 备注: {entry['note']}")
    return _engine


def get_engine() -> Engine:
    """获取当前引擎，未配置时自动以默认参数初始化。"""
    if _engine is None:
        configure()
    return _engine  # type: ignore[return-value]


def get_session_factory() -> sessionmaker[Session]:
    """获取当前会话工厂，未配置时自动初始化。"""
    if _session_factory is None:
        configure()
    return _session_factory  # type: ignore[return-value]


def get_session() -> Session:
    """创建一个新的数据库会话（调用方负责 close 或使用 context manager）。"""
    return get_session_factory()()
