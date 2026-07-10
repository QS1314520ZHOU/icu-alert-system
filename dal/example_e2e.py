"""
端到端示例：在本地 PostgreSQL 上跑通 DAL 全流程
=================================================

流程：
    1. 配置本地 PostgreSQL 连接
    2. 建表（如已存在则跳过）
    3. 插入测试数据
    4. 用 QueryCondition 重现 Java 原型查询
    5. 演示分页、排序、投影、计数、更新、删除
    6. 清理测试表

运行方式：
    # 确保本地 PostgreSQL 运行中，数据库 "postgres" 可访问
    # 可通过环境变量覆盖连接信息：
    #   DAL_USER=xxx DAL_PASSWORD=yyy DAL_DB=mydb python -m dal.example_e2e

    python -m dal.example_e2e
"""

from __future__ import annotations

import sys
import os

# 确保 dal 包可被导入（当直接运行此文件时）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dal.config import configure, get_engine
from dal.models import Base, Patient
from dal.condition import QC
from dal.operation import OperationDatabase as DB


def main() -> None:
    print("=" * 70)
    print("  DAL 统一数据访问层 — 端到端示例")
    print("=" * 70)

    # ── Step 1: 配置连接 ──────────────────────────────────────────
    # 默认连本地 PostgreSQL；可通过 DAL_DATABASE_URL 环境变量覆盖
    # 例: DAL_DATABASE_URL=postgresql+psycopg2://user:pwd@localhost:5432/mydb
    engine = configure("postgresql", echo=False)

    # ── Step 2: 建表 ──────────────────────────────────────────────
    print("\n[Step 2] 建表 patient ...")
    Patient.__table__.drop(engine, checkfirst=True)
    Patient.__table__.create(engine)
    print("  ✅ 表 patient 已创建")

    # ── Step 3: 插入测试数据 ──────────────────────────────────────
    print("\n[Step 3] 插入测试数据 ...")
    test_data = [
        Patient(
            saas_org_code="ORG001",
            saas_department_code="DEPT_ICU",
            name="张三",
            age=45,
            gender="男",
            status=1,
        ),
        Patient(
            saas_org_code="ORG001",
            saas_department_code="DEPT_ICU",
            name="李四",
            age=32,
            gender="女",
            status=1,
        ),
        Patient(
            saas_org_code="ORG001",
            saas_department_code="DEPT_ER",
            name="王五",
            age=67,
            gender="男",
            status=1,
        ),
        Patient(
            saas_org_code="ORG002",
            saas_department_code="DEPT_ICU",
            name="赵六",
            age=28,
            gender="女",
            status=1,
        ),
        Patient(
            saas_org_code="ORG002",
            saas_department_code="DEPT_ER",
            name="钱七",
            age=55,
            gender="男",
            status=0,   # 无效状态
        ),
    ]
    DB.insert(test_data)
    print(f"  ✅ 已插入 {len(test_data)} 条记录")

    # ── Step 4: 重现 Java 原型查询 ────────────────────────────────
    #
    # Java 原型:
    #   OperationDatabase.queryList(
    #       Patient.class,
    #       new QueryCondition()
    #           .in("saasOrgCode", Arrays.asList("ORG001", "ORG002"))
    #           .in("saasDepartmentCode", Arrays.asList("DEPT_ICU"))
    #   )
    #
    # Python DAL 等价写法：
    print("\n[Step 4] 重现 Java 原型查询")
    print("  条件: saas_org_code IN ('ORG001','ORG002') "
          "AND saas_department_code IN ('DEPT_ICU')")

    org_codes = "ORG001,ORG002"
    dept_codes = "DEPT_ICU"

    condition = (
        QC()
        .in_("saas_org_code", org_codes.split(","))
        .in_("saas_department_code", dept_codes.split(","))
    )

    results = DB.query_list(Patient, condition)
    print(f"\n  查询结果 ({len(results)} 条):")
    for p in results:
        print(f"    {p}")

    # ── Step 5: 更多功能演示 ──────────────────────────────────────

    # 5a. 统计
    print("\n[Step 5a] 统计有效患者数")
    total = DB.count(Patient, QC().eq("status", 1))
    print(f"  有效患者: {total} 人")

    # 5b. 查询单条（建议指定 order_by 确保结果稳定）
    print("\n[Step 5b] 查询单条记录 (id=1, order_by=['id'])")
    one = DB.query_one(Patient, QC().eq("id", 1), order_by=["id"])
    print(f"  结果: {one}")

    # 5c. 分页 + 排序
    print("\n[Step 5c] 分页查询: page=1, size=2, 按 age 降序")
    paged = DB.query_list(
        Patient,
        QC().eq("status", 1),
        order_by=["age desc"],
        page=1,
        size=2,
    )
    for p in paged:
        print(f"    {p.name}, age={p.age}")

    # 5d. 字段投影
    print("\n[Step 5d] 字段投影: 只查 name, age")
    projected = DB.query_list(
        Patient,
        QC().eq("status", 1),
        columns=["name", "age"],
    )
    for row in projected:
        print(f"    name={row.name}, age={row.age}")

    # 5e. 复合条件 (OR)
    print("\n[Step 5e] 复合条件: age>60 OR gender='女'")
    complex_cond = QC().or_(
        QC().gt("age", 60),
        QC().eq("gender", "女"),
    )
    complex_results = DB.query_list(Patient, complex_cond)
    for p in complex_results:
        print(f"    {p.name}, age={p.age}, gender={p.gender}")

    # 5f. BETWEEN
    print("\n[Step 5f] BETWEEN: 30 <= age <= 50")
    between_results = DB.query_list(
        Patient,
        QC().between("age", 30, 50),
    )
    for p in between_results:
        print(f"    {p.name}, age={p.age}")

    # 5g. LIKE
    print("\n[Step 5g] LIKE: name 包含 '三'")
    like_results = DB.query_list(
        Patient,
        QC().like("name", "%三%"),
    )
    for p in like_results:
        print(f"    {p.name}")

    # 5h. 更新
    print("\n[Step 5h] 更新: 将张三的年龄改为 46")
    affected = DB.update(
        Patient,
        QC().eq("name", "张三"),
        {"age": 46},
    )
    print(f"  影响行数: {affected}")
    updated = DB.query_one(Patient, QC().eq("name", "张三"))
    print(f"  更新后: {updated.name}, age={updated.age}")

    # 5i. 删除
    print("\n[Step 5i] 删除: status=0 的记录")
    deleted = DB.delete(Patient, QC().eq("status", 0))
    print(f"  影响行数: {deleted}")

    # 验证删除后计数
    remaining = DB.count(Patient)
    print(f"  剩余记录: {remaining}")

    # 5j. 事务示例
    print("\n[Step 5j] 事务示例: 在同一事务中插入两条记录")
    with DB.transaction() as session:
        session.add(Patient(
            saas_org_code="ORG003",
            saas_department_code="DEPT_ICU",
            name="孙八",
            age=38,
            gender="男",
            status=1,
        ))
        session.add(Patient(
            saas_org_code="ORG003",
            saas_department_code="DEPT_ER",
            name="周九",
            age=42,
            gender="女",
            status=1,
        ))
    print(f"  事务提交后总记录数: {DB.count(Patient)}")

    # ── Step 6: 清理 ──────────────────────────────────────────────
    print("\n[Step 6] 清理测试表")
    Patient.__table__.drop(engine, checkfirst=True)
    print("  ✅ 表 patient 已删除")

    print("\n" + "=" * 70)
    print("  ✅ 全部流程跑通！DAL 模块功能正常。")
    print("=" * 70)


if __name__ == "__main__":
    main()
