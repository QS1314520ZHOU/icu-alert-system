"""S-AKI 字段映射适配层 - 不同医院字段名称映射到标准化字段。"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("icu-alert")


class _FieldEntry:
    """单个字段映射条目。"""

    __slots__ = ("standard_name", "hospital_fields", "collection", "unit_hint", "description")

    def __init__(
        self,
        standard_name: str,
        hospital_fields: list[str],
        collection: str,
        unit_hint: str = "",
        description: str = "",
    ) -> None:
        self.standard_name = standard_name
        self.hospital_fields = hospital_fields
        self.collection = collection
        self.unit_hint = unit_hint
        self.description = description

    def to_dict(self) -> dict[str, Any]:
        return {
            "standard_name": self.standard_name,
            "hospital_fields": list(self.hospital_fields),
            "collection": self.collection,
            "unit_hint": self.unit_hint,
            "description": self.description,
        }


# ---------------------------------------------------------------------------
# 默认字段映射（覆盖常见医院信息系统字段名）
# ---------------------------------------------------------------------------
DEFAULT_ENTRIES: list[_FieldEntry] = [
    # ---- patient 集合 ----
    _FieldEntry("patient_id", ["hisPid", "_id", "patientId", "patient_id", "pid"], "patient", "", "患者唯一标识"),
    _FieldEntry("admit_time", ["icuAdmissionTime", "admissionTime", "admitTime", "inTime", "createTime"], "patient", "", "入ICU时间"),
    _FieldEntry("discharge_time", ["dischargeTime", "outTime", "endTime"], "patient", "", "出ICU时间"),
    _FieldEntry("department", ["hisDept", "dept", "department", "dept_name"], "patient", "", "科室名称"),
    _FieldEntry("dept_code", ["deptCode", "dept_code", "departmentCode"], "patient", "", "科室代码"),
    _FieldEntry("diagnosis", ["clinicalDiagnosis", "admissionDiagnosis", "diagnosis"], "patient", "", "诊断"),
    _FieldEntry("weight", ["weight", "bodyWeight", "body_weight", "weightKg", "weight_kg"], "patient", "kg", "体重"),
    _FieldEntry("sex", ["sex", "gender", "patientSex"], "patient", "", "性别"),
    _FieldEntry("age", ["age", "patientAge"], "patient", "years", "年龄"),
    _FieldEntry("status", ["status", "patientStatus"], "patient", "", "患者状态"),

    # ---- labResult 集合 ----
    _FieldEntry("creatinine", ["cr", "CREA", "creatinine", "肌酐", "SCr", "scr"], "labResult", "umol/L", "血清肌酐"),
    _FieldEntry("bun", ["bun", "BUN", "urea", "尿素氮", "Urea"], "labResult", "mmol/L", "血尿素氮"),
    _FieldEntry("wbc", ["wbc", "WBC", "白细胞", "leukocyte"], "labResult", "10^9/L", "白细胞计数"),
    _FieldEntry("pct", ["pct", "PCT", "降钙素原", "procalcitonin"], "labResult", "ng/mL", "降钙素原"),
    _FieldEntry("crp", ["crp", "CRP", "C反应蛋白", "c-reactive protein"], "labResult", "mg/L", "C反应蛋白"),
    _FieldEntry("lactate", ["lac", "LAC", "乳酸", "lactate"], "labResult", "mmol/L", "血乳酸"),
    _FieldEntry("platelet", ["plt", "PLT", "血小板", "platelet"], "labResult", "10^9/L", "血小板计数"),
    _FieldEntry("bilirubin", ["bil", "BIL", "胆红素", "bilirubin", "TBIL"], "labResult", "umol/L", "总胆红素"),
    _FieldEntry("alt", ["alt", "ALT", "谷丙转氨酶"], "labResult", "U/L", "丙氨酸氨基转移酶"),
    _FieldEntry("ast", ["ast", "AST", "谷草转氨酶"], "labResult", "U/L", "天门冬氨酸氨基转移酶"),
    _FieldEntry("pao2", ["pao2", "PO2", "氧分压", "paO2"], "labResult", "mmHg", "动脉血氧分压"),
    _FieldEntry("fio2", ["fio2", "FiO2", "吸入氧浓度"], "labResult", "%", "吸入氧浓度"),
    _FieldEntry("gcs", ["gcs", "GCS", "格拉斯哥评分"], "labResult", "", "格拉斯哥昏迷评分"),

    # ---- vitalSign 集合 ----
    _FieldEntry("hr", ["param_HR", "param_PR", "HR", "心率"], "vitalSign", "bpm", "心率"),
    _FieldEntry("sbp", ["param_nibp_s", "param_ibp_s", "param_abp_s", "SBP"], "vitalSign", "mmHg", "收缩压"),
    _FieldEntry("map", ["param_nibp_m", "param_ibp_m", "param_abp_m", "MAP"], "vitalSign", "mmHg", "平均动脉压"),
    _FieldEntry("dbp", ["param_nibp_d", "param_ibp_d", "param_abp_d", "DBP"], "vitalSign", "mmHg", "舒张压"),
    _FieldEntry("rr", ["param_resp", "RR", "呼吸频率"], "vitalSign", "次/min", "呼吸频率"),
    _FieldEntry("spo2", ["param_spo2", "SpO2", "血氧饱和度"], "vitalSign", "%", "脉搏血氧饱和度"),
    _FieldEntry("temp", ["param_T", "Temp", "体温", "温度"], "vitalSign", "℃", "体温"),

    # ---- drug 集合 ----
    _FieldEntry("vasopressor_norepinephrine", ["去甲肾上腺素", "norepinephrine", "norepi", "NE"], "drug", "", "去甲肾上腺素"),
    _FieldEntry("antibiotic_meropenem", ["美罗培南", "meropenem", "MEM"], "drug", "", "美罗培南"),
    _FieldEntry("antibiotic_vancomycin", ["万古霉素", "vancomycin", "VAN"], "drug", "", "万古霉素"),
    _FieldEntry("antibiotic_piperacillin", ["哌拉西林他唑巴坦", "piperacillin-tazobactam", "TZP"], "drug", "", "哌拉西林他唑巴坦"),
    _FieldEntry("antibiotic_cefepime", ["头孢吡肟", "cefepime", "FEP"], "drug", "", "头孢吡肟"),
]

# 按 collection 分组的快速索引
_COLLECTION_INDEX: dict[str, list[_FieldEntry]] = {}
for _e in DEFAULT_ENTRIES:
    _COLLECTION_INDEX.setdefault(_e.collection, []).append(_e)


class FieldMappingService:
    """字段映射适配层。

    支持从 MongoDB 动态加载映射，若数据库无自定义映射则回退到默认值。
    """

    def __init__(self, db: Any = None) -> None:
        self._db = db
        self._custom_cache: dict[str, list[dict[str, Any]]] | None = None

    async def _load_custom(self) -> dict[str, list[dict[str, Any]]]:
        if self._custom_cache is not None:
            return self._custom_cache
        if self._db is None:
            self._custom_cache = {}
            return self._custom_cache
        try:
            col = self._db.col("saki_field_mappings")
            cursor = col.find({}, {"_id": 0})
            result: dict[str, list[dict[str, Any]]] = {}
            async for doc in cursor:
                coll = str(doc.get("collection", ""))
                result.setdefault(coll, []).append(doc)
            self._custom_cache = result
        except Exception as exc:
            logger.warning("加载自定义字段映射失败: %s", exc)
            self._custom_cache = {}
        return self._custom_cache

    async def resolve_field(self, collection: str, standard_name: str) -> list[str]:
        """返回指定集合中某个标准字段对应的所有可能医院字段名。"""
        custom = await self._load_custom()
        for entry in custom.get(collection, []):
            if entry.get("standard_name") == standard_name:
                fields = entry.get("hospital_fields", [])
                if fields:
                    return list(fields)
        for entry in _COLLECTION_INDEX.get(collection, []):
            if entry.standard_name == standard_name:
                return list(entry.hospital_fields)
        return [standard_name]

    async def get_all_mappings(self, collection: str | None = None) -> list[dict[str, Any]]:
        """获取所有字段映射。"""
        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        custom = await self._load_custom()

        if collection:
            for entry in custom.get(collection, []):
                key = f"{entry.get('collection')}:{entry.get('standard_name')}"
                if key not in seen:
                    result.append(entry)
                    seen.add(key)
            for entry in _COLLECTION_INDEX.get(collection, []):
                if entry.standard_name not in {e.get("standard_name") for e in result}:
                    result.append(entry.to_dict())
        else:
            for entries in custom.values():
                for entry in entries:
                    key = f"{entry.get('collection')}:{entry.get('standard_name')}"
                    if key not in seen:
                        result.append(entry)
                        seen.add(key)
            for coll, entries in _COLLECTION_INDEX.items():
                for entry in entries:
                    if f"{coll}:{entry.standard_name}" not in seen:
                        result.append(entry.to_dict())
        return result

    async def update_mapping(
        self,
        collection: str,
        standard_name: str,
        hospital_fields: list[str],
        description: str = "",
    ) -> dict[str, Any]:
        """更新或创建字段映射。"""
        if self._db is None:
            raise RuntimeError("数据库未连接，无法更新映射")
        col = self._db.col("saki_field_mappings")
        now = datetime.now(timezone.utc)
        doc = {
            "collection": collection,
            "standard_name": standard_name,
            "hospital_fields": hospital_fields,
            "description": description,
            "updated_at": now,
        }
        await col.update_one(
            {"collection": collection, "standard_name": standard_name},
            {"$set": doc},
            upsert=True,
        )
        self._custom_cache = None
        return doc
