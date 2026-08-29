"""S-AKI 演示数据种子 - 生成符合临床逻辑的模拟数据。"""
from __future__ import annotations

import logging
import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger("icu-alert")

TEST_PREFIX = "SAKI_TEST_"


async def seed_saki_demo_data(db: Any, count: int = 50) -> dict[str, Any]:
    """生成 S-AKI 演示数据。"""
    now = datetime.now(timezone.utc)
    patients = []
    lab_results = []
    vitals = []
    drugs = []
    crrt_records = []
    saki_cases = []

    for i in range(count):
        pid = f"{TEST_PREFIX}{uuid.uuid4().hex[:8]}"
        is_saki = random.random() < 0.60
        has_sepsis = is_saki or random.random() < 0.10
        has_aki = is_saki or random.random() < 0.25

        age = random.randint(18, 90)
        sex = random.choice(["M", "F"])
        weight = random.uniform(45, 110)
        admit_time = now - timedelta(days=random.randint(3, 30))
        dept = random.choice(["ICU-A", "ICU-B", "ICU-C", "SICU", "MICU"])

        # 患者文档
        patient_doc = {
            "_id": pid,
            "name": f"{TEST_PREFIX}Patient_{i+1:03d}",
            "hisPid": pid,
            "hisBed": f"{dept}-{random.randint(1, 20):02d}",
            "dept": dept,
            "hisDept": dept,
            "deptCode": dept,
            "status": "active",
            "sex": sex,
            "age": age,
            "weight": round(weight, 1),
            "bodyWeight": round(weight, 1),
            "clinicalDiagnosis": _gen_diagnosis(has_sepsis, has_aki),
            "admissionDiagnosis": _gen_diagnosis(has_sepsis, has_aki),
            "icuAdmissionTime": admit_time,
            "admissionTime": admit_time,
            "test_data": True,
            "test_prefix": TEST_PREFIX,
            "created_at": now,
        }
        patients.append(patient_doc)

        # 肌酐序列（7 天内）
        baseline_cr = random.uniform(50, 100) if sex == "F" else random.uniform(60, 120)
        cr_trajectory = _gen_creatinine_trajectory(baseline_cr, has_aki, has_sepsis, admit_time, now)
        for t, val in cr_trajectory:
            lab_results.append({
                "_id": f"{TEST_PREFIX}lab_cr_{pid}_{t.strftime('%Y%m%d%H%M')}",
                "patientId": pid,
                "patient_id": pid,
                "testName": "肌酐",
                "test_code": "cr",
                "code": "cr",
                "result": str(round(val, 1)),
                "value": round(val, 1),
                "unit": "umol/L",
                "reportTime": t,
                "sampleTime": t,
                "test_data": True,
                "test_prefix": TEST_PREFIX,
            })

        # WBC, PCT, CRP
        if has_sepsis:
            for lab_code, lab_name, base_val, high_val in [
                ("wbc", "白细胞", 4, 20), ("pct", "降钙素原", 0.1, 15),
                ("crp", "C反应蛋白", 5, 200),
            ]:
                val = random.uniform(base_val, high_val)
                lab_results.append({
                    "_id": f"{TEST_PREFIX}lab_{lab_code}_{pid}",
                    "patientId": pid, "patient_id": pid,
                    "testName": lab_name, "test_code": lab_code, "code": lab_code,
                    "result": str(round(val, 2)), "value": round(val, 2),
                    "unit": "", "reportTime": admit_time + timedelta(hours=random.randint(1, 24)),
                    "test_data": True, "test_prefix": TEST_PREFIX,
                })

        # 生命体征
        for hour_offset in range(0, 72, 6):
            t = admit_time + timedelta(hours=hour_offset)
            vitals.append({
                "_id": f"{TEST_PREFIX}vital_{pid}_{hour_offset}",
                "patientId": pid, "patient_id": pid,
                "param_code": "param_HR", "value": random.randint(60, 130),
                "recordTime": t, "test_data": True, "test_prefix": TEST_PREFIX,
            })
            map_val = random.uniform(55, 95) if has_sepsis else random.uniform(70, 100)
            vitals.append({
                "_id": f"{TEST_PREFIX}vital_map_{pid}_{hour_offset}",
                "patientId": pid, "patient_id": pid,
                "param_code": "param_nibp_m", "value": round(map_val, 1),
                "recordTime": t, "test_data": True, "test_prefix": TEST_PREFIX,
            })

        # 药物
        if has_sepsis:
            drugs.append({
                "_id": f"{TEST_PREFIX}drug_abx_{pid}",
                "patientId": pid, "patient_id": pid,
                "drugName": "美罗培南", "drug_name": "美罗培南",
                "dose": "1g q8h", "route": "IV",
                "startTime": admit_time + timedelta(hours=random.randint(1, 6)),
                "test_data": True, "test_prefix": TEST_PREFIX,
            })
        if has_aki and random.random() < 0.4:
            crrt_records.append({
                "_id": f"{TEST_PREFIX}crrt_{pid}",
                "patientId": pid, "patient_id": pid,
                "startTime": admit_time + timedelta(hours=random.randint(12, 48)),
                "mode": "CVVHDF", "flow_rate": random.randint(25, 35),
                "test_data": True, "test_prefix": TEST_PREFIX,
            })

        # S-AKI 病例
        saki_stage = 0
        if has_aki:
            saki_stage = random.choices([1, 2, 3], weights=[0.5, 0.3, 0.2])[0]
        saki_cases.append({
            "patient_id": pid,
            "patient_name": patient_doc["name"],
            "department": dept,
            "dept_code": dept,
            "is_saki": is_saki,
            "saki_probability": "high" if is_saki and saki_stage >= 2 else ("moderate" if is_saki else "none"),
            "aki_stage": saki_stage,
            "sepsis_phenotype": {"is_sepsis": has_sepsis, "sofa_score": random.randint(2, 12), "sofa_delta": random.randint(0, 8)},
            "aki_phenotype": {"aki_stage": saki_stage, "creatinine_baseline": round(baseline_cr, 1)},
            "temporal_association": {"associated": is_saki, "time_delta_hours": random.uniform(-12, 168)},
            "risk_factors": [],
            "review_status": "pending",
            "version": "v1.0.0",
            "calc_time": now,
            "created_at": now,
            "updated_at": now,
            "test_data": True,
            "test_prefix": TEST_PREFIX,
        })

    # 批量插入
    collections_and_docs = [
        ("patient", patients),
        ("labResult", lab_results),
        ("vitalSign", vitals),
        ("drug", drugs),
        ("crrt", crrt_records),
        ("saki_cases", saki_cases),
    ]
    summary: dict[str, Any] = {"counts": {}}
    for coll_name, docs in collections_and_docs:
        if docs:
            await db.col(coll_name).insert_many(docs)
            summary["counts"][coll_name] = len(docs)

    logger.info("✅ S-AKI 演示数据已生成: %d 患者", count)
    return summary


async def cleanup_saki_test_data(db: Any) -> dict[str, Any]:
    """清除所有 S-AKI 测试数据。"""
    collections = ["patient", "labResult", "vitalSign", "drug", "crrt",
                    "saki_cases", "saki_cohorts", "saki_snapshots", "saki_audit_log"]
    summary: dict[str, Any] = {"counts": {}}
    for coll_name in collections:
        result = await db.col(coll_name).delete_many({"test_data": True})
        summary["counts"][coll_name] = result.deleted_count
    logger.info("✅ S-AKI 测试数据已清理")
    return summary


async def ensure_saki_disease_definition(db: Any) -> dict[str, Any]:
    """确保 S-AKI 病种定义已存在。"""
    doc = {
        "id": "saki-001",
        "code": "S-AKI",
        "name": "脓毒症相关急性肾损伤",
        "english_name": "Sepsis-Associated Acute Kidney Injury",
        "short_name": "S-AKI",
        "category_id": "renal",
        "description": "脓毒症（Sepsis-3定义）合并急性肾损伤（KDIGO 2012分期）的患者群体",
        "diagnostic_criteria": "脓毒症（Sepsis-3: 感染 + SOFA delta >= 2）+ AKI（KDIGO: SCr升高或尿量减少）",
        "status": "active",
        "version": "v1.0.0",
        "test_data": True,
        "test_prefix": TEST_PREFIX,
        "created_at": datetime.now(timezone.utc),
    }
    await db.col("diseases").update_one(
        {"id": "saki-001"}, {"$set": doc}, upsert=True,
    )
    return doc


def _gen_diagnosis(has_sepsis: bool, has_aki: bool) -> str:
    parts = []
    if has_sepsis:
        parts.append(random.choice([
            "脓毒症", "重症脓毒症", "脓毒性休克", "肺部感染", "腹腔感染",
            "泌尿系感染", "导管相关感染", "血流感染",
        ]))
    if has_aki:
        parts.append("急性肾损伤")
    parts.append(random.choice(["高血压", "2型糖尿病", "冠心病", "COPD", "脑血管病"]))
    return "，".join(parts)


def _gen_creatinine_trajectory(baseline: float, has_aki: bool, has_sepsis: bool, admit: datetime, now: datetime) -> list[tuple[datetime, float]]:
    trajectory = []
    if has_aki:
        peak_multiplier = random.choice([1.5, 2.0, 2.5, 3.0, 4.0])
        peak_time_offset = random.randint(12, 72)
        for h in range(0, min(168, int((now - admit).total_seconds() / 3600) + 1), 8):
            t = admit + timedelta(hours=h)
            if h < peak_time_offset:
                progress = h / max(peak_time_offset, 1)
                val = baseline + (baseline * peak_multiplier - baseline) * progress
            else:
                recovery = (h - peak_time_offset) / max(168 - peak_time_offset, 1)
                val = baseline * peak_multiplier * (1 - recovery * 0.6) + baseline * 0.6 * recovery
            val += random.gauss(0, baseline * 0.05)
            trajectory.append((t, max(baseline * 0.5, val)))
    else:
        for h in range(0, min(168, int((now - admit).total_seconds() / 3600) + 1), 12):
            t = admit + timedelta(hours=h)
            val = baseline + random.gauss(0, baseline * 0.05)
            trajectory.append((t, max(20, val)))
    return trajectory
