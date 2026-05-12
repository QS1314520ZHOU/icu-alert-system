from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

from app.services.audit_service import write_audit_log
from app.utils.serialization import serialize_doc


DEFAULT_MODULES = [
    {"key": "clinical_workflow", "name": "ICU智能协同工作台", "enabled": True, "description": "角色首页、主任晨会、患者任务和交班事件链。"},
    {"key": "scanner_health", "name": "规则健康", "enabled": True, "description": "告警反馈闭环、PPV、override 和阈值建议。"},
    {"key": "rounding", "name": "医生查房", "enabled": True, "description": "查房问题清单和查房报告。"},
    {"key": "respiratory", "name": "呼吸治疗", "enabled": True, "description": "撤机灯、SBT、气道任务和呼吸机参数。"},
    {"key": "nutrition", "name": "营养支持", "enabled": True, "description": "NRS2002/NUTRIC、EN/PN、血糖和再喂养风险。"},
    {"key": "mdt", "name": "MDT会诊", "enabled": True, "description": "多学科会诊、人体图和决议闭环。"},
    {"key": "ai", "name": "AI能力", "enabled": True, "description": "AI摘要、风险预测、相似病例和问诊。"},
]

DEFAULT_AI_CONFIG = {
    "enabled": True,
    "fast_model": "",
    "medical_model": "",
    "fallback_model": "",
    "reasoning_model": "",
    "routes": {"fast": "", "medical": "", "reasoning": "", "long_context": "", "fallback": ""},
    "providers": [],
    "temperature": 0.1,
    "max_tokens": 1024,
    "timeout": 30,
    "circuit_breaker": {"failure_threshold": 3, "cooldown_seconds": 180},
}

TRAJECTORY_CODE_OPTIONS = [
    {"code": "HR", "label": "心率", "unit": "bpm", "series_type": "continuous", "default_visible": True},
    {"code": "MAP", "label": "平均动脉压", "unit": "mmHg", "series_type": "continuous", "default_visible": True},
    {"code": "SBP", "label": "收缩压", "unit": "mmHg", "series_type": "continuous", "default_visible": True},
    {"code": "DBP", "label": "舒张压", "unit": "mmHg", "series_type": "continuous", "default_visible": True},
    {"code": "SpO2", "label": "血氧饱和度", "unit": "%", "series_type": "continuous", "default_visible": True},
    {"code": "RR", "label": "呼吸频率", "unit": "/min", "series_type": "continuous", "default_visible": True},
    {"code": "Temp", "label": "体温", "unit": "℃", "series_type": "continuous", "default_visible": True, "recommended_horizon_hours": 12},
    {"code": "EtCO2", "label": "呼气末二氧化碳", "unit": "mmHg", "series_type": "continuous", "default_visible": True, "requires_context": ["intubated"]},
    {"code": "CVP", "label": "中心静脉压", "unit": "cmH2O", "series_type": "continuous", "default_visible": False, "data_quality_gate": True},
    {"code": "ICP", "label": "颅内压", "unit": "mmHg", "series_type": "continuous", "default_visible": False, "data_quality_gate": True},
    {"code": "Lactate", "label": "乳酸", "unit": "mmol/L", "series_type": "discrete_trend", "default_visible": False},
]

DEFAULT_TRAJECTORY_FORECAST_CONFIG = {
    "enabled": True,
    "default_codes": ["HR", "MAP", "SBP", "DBP", "SpO2", "RR", "Temp", "EtCO2"],
    "alert_enabled": False,
    "alert_codes": ["MAP", "SpO2", "RR", "Temp", "EtCO2"],
    "horizon_hours": 6,
    "scope": "global",
    "version": 1,
    "calibration_version": "uncalibrated-v1",
    "thresholds": [
        {"code": "MAP", "operator": "<", "threshold": 65, "probability": 0.70, "severity": "high", "horizon_hours": 4},
        {"code": "SpO2", "operator": "<", "threshold": 90, "probability": 0.70, "severity": "high", "horizon_hours": 4},
        {"code": "RR", "operator": ">", "threshold": 30, "probability": 0.70, "severity": "warning", "horizon_hours": 4},
        {"code": "Temp", "operator": ">", "threshold": 38.5, "probability": 0.80, "severity": "warning", "horizon_hours": 6},
        {"code": "EtCO2", "operator": "<", "threshold": 25, "probability": 0.70, "severity": "warning", "horizon_hours": 4},
    ],
}

DEFAULT_FIELD_MAPPINGS = [
    {"source_name": "deviceCap", "source_code": "param_HuXiMoShi", "standard_concept": "vent_mode", "unit": "", "module": "respiratory", "enabled": True, "description": "通气模式"},
    {"source_name": "deviceCap", "source_code": "param_vent_mode", "standard_concept": "vent_mode", "unit": "", "module": "respiratory", "enabled": True, "description": "通气模式备用字段"},
    {"source_name": "deviceCap", "source_code": "param_FiO2", "standard_concept": "fio2", "unit": "%", "module": "respiratory", "enabled": True, "description": "吸入氧浓度"},
    {"source_name": "deviceCap", "source_code": "param_fio2", "standard_concept": "fio2", "unit": "%", "module": "respiratory", "enabled": True, "description": "吸入氧浓度备用字段"},
    {"source_name": "deviceCap", "source_code": "param_vent_measure_peep", "standard_concept": "peep_measured", "unit": "cmH2O", "module": "respiratory", "enabled": True, "description": "实测 PEEP"},
    {"source_name": "deviceCap", "source_code": "param_vent_peep", "standard_concept": "peep_set", "unit": "cmH2O", "module": "respiratory", "enabled": True, "description": "设置 PEEP"},
    {"source_name": "deviceCap", "source_code": "param_vent_vt", "standard_concept": "vte", "unit": "mL", "module": "respiratory", "enabled": True, "description": "呼出潮气量"},
    {"source_name": "deviceCap", "source_code": "param_vent_vti", "standard_concept": "vti", "unit": "mL", "module": "respiratory", "enabled": True, "description": "吸入潮气量"},
    {"source_name": "deviceCap", "source_code": "param_vent_set_vt", "standard_concept": "vt_set", "unit": "mL", "module": "respiratory", "enabled": True, "description": "设置潮气量"},
    {"source_name": "deviceCap", "source_code": "param_vent_pip", "standard_concept": "pip", "unit": "cmH2O", "module": "respiratory", "enabled": True, "description": "气道峰压"},
    {"source_name": "deviceCap", "source_code": "param_vent_plat_pressure", "standard_concept": "pplat", "unit": "cmH2O", "module": "respiratory", "enabled": True, "description": "平台压"},
    {"source_name": "deviceCap", "source_code": "param_vent_resp", "standard_concept": "rr_measured", "unit": "/min", "module": "respiratory", "enabled": True, "description": "呼吸机实测呼吸频率"},
    {"source_name": "deviceCap", "source_code": "param_HuXiPinLv", "standard_concept": "rr_set", "unit": "/min", "module": "respiratory", "enabled": True, "description": "设置呼吸频率"},
    {"source_name": "deviceCap", "source_code": "param_vent_pc", "standard_concept": "pressure_control", "unit": "cmH2O", "module": "respiratory", "enabled": True, "description": "压力控制水平"},
    {"source_name": "deviceCap", "source_code": "param_vent_ps", "standard_concept": "pressure_support", "unit": "cmH2O", "module": "respiratory", "enabled": True, "description": "压力支持水平"},
    {"source_name": "deviceCap", "source_code": "param_vent_set_PeakFlow", "standard_concept": "peak_flow", "unit": "L/min", "module": "respiratory", "enabled": True, "description": "设置峰流速"},
    {"source_name": "deviceCap", "source_code": "param_vent_P0.1", "standard_concept": "p01", "unit": "cmH2O", "module": "respiratory", "enabled": True, "description": "P0.1"},
    {"source_name": "deviceCap", "source_code": "param_vent_C_STAT", "standard_concept": "static_compliance", "unit": "mL/cmH2O", "module": "respiratory", "enabled": True, "description": "静态顺应性"},
    {"source_name": "deviceCap", "source_code": "param_vent_pause_C_STAT", "standard_concept": "static_compliance", "unit": "mL/cmH2O", "module": "respiratory", "enabled": True, "description": "暂停法静态顺应性"},
    {"source_name": "deviceCap", "source_code": "param_jingTaiShunYingXing", "standard_concept": "static_compliance", "unit": "mL/cmH2O", "module": "respiratory", "enabled": True, "description": "静态顺应性中文字段"},
    {"source_name": "deviceCap", "source_code": "param_TiWei", "standard_concept": "position", "unit": "", "module": "respiratory", "enabled": True, "description": "体位"},
    {"source_name": "deviceCap", "source_code": "param_qiDaoZuLi", "standard_concept": "airway_resistance", "unit": "cmH2O/L/s", "module": "respiratory", "enabled": True, "description": "气道阻力"},
    {"source_name": "bedside", "source_code": "param_spo2", "standard_concept": "spo2", "unit": "%", "module": "respiratory", "enabled": True, "description": "血氧饱和度"},
    {"source_name": "bedside", "source_code": "param_resp", "standard_concept": "rr_measured", "unit": "/min", "module": "respiratory", "enabled": True, "description": "床旁呼吸频率"},
    {"source_name": "bedside", "source_code": "param_hfnc_flow", "standard_concept": "hfnc_flow", "unit": "L/min", "module": "respiratory", "enabled": True, "description": "HFNC 流量"},
    {"source_name": "bedside", "source_code": "param_oxygen_flow", "standard_concept": "hfnc_flow", "unit": "L/min", "module": "respiratory", "enabled": True, "description": "氧疗流量"},
    {"source_name": "bedside", "source_code": "param_niv_ipap", "standard_concept": "niv_ipap", "unit": "cmH2O", "module": "respiratory", "enabled": True, "description": "NIV IPAP"},
    {"source_name": "bedside", "source_code": "param_niv_epap", "standard_concept": "niv_epap", "unit": "cmH2O", "module": "respiratory", "enabled": True, "description": "NIV EPAP"},
    {"source_name": "bedside", "source_code": "param_niv_leak", "standard_concept": "niv_leak", "unit": "L/min", "module": "respiratory", "enabled": True, "description": "NIV 漏气量"},
]


class RuntimeConfigService:
    def __init__(self, db) -> None:
        self.db = db

    async def _get_config_doc(self, key: str, default_value: Any) -> dict[str, Any]:
        doc = await self.db.col("runtime_configs").find_one({"key": key})
        if doc:
            return serialize_doc(doc)
        now = datetime.now()
        seed = {"key": key, "value": deepcopy(default_value), "created_at": now, "updated_at": now}
        await self.db.col("runtime_configs").insert_one(seed)
        return serialize_doc(seed)

    async def get_value(self, key: str, default_value: Any = None) -> Any:
        doc = await self._get_config_doc(key, default_value)
        return doc.get("value")

    async def overview(self) -> dict[str, Any]:
        modules_doc = await self._get_config_doc("modules", DEFAULT_MODULES)
        ai_doc = await self._get_config_doc("ai", DEFAULT_AI_CONFIG)
        trajectory_doc = await self._get_config_doc("trajectory_forecast", DEFAULT_TRAJECTORY_FORECAST_CONFIG)
        await self.ensure_default_field_mappings()
        rules = [serialize_doc(row) async for row in self.db.col("alert_rules").find({}).sort([("category", 1), ("rule_id", 1)]).limit(300)]
        mappings = [serialize_doc(row) async for row in self.db.col("field_mapping").find({}).sort([("standard_concept", 1), ("source_name", 1)]).limit(500)]
        return {
            "modules": modules_doc.get("value") or [],
            "ai": ai_doc.get("value") or {},
            "trajectory_forecast": trajectory_doc.get("value") or {},
            "trajectory_code_options": TRAJECTORY_CODE_OPTIONS,
            "field_mapping_defaults": DEFAULT_FIELD_MAPPINGS,
            "alert_rules": rules,
            "field_mappings": mappings,
            "generated_at": datetime.now(),
        }

    async def ensure_default_field_mappings(self) -> None:
        now = datetime.now()
        for item in DEFAULT_FIELD_MAPPINGS:
            await self.db.col("field_mapping").update_one(
                {"source_code": item["source_code"], "source_name": item["source_name"]},
                {
                    "$setOnInsert": {**item, "created_at": now},
                    "$set": {"default_module": item.get("module"), "default_standard_concept": item.get("standard_concept")},
                },
                upsert=True,
            )

    async def history(self, key: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        query: dict[str, Any] = {}
        if key and key != "all":
            query["key"] = str(key)
        rows = self.db.col("runtime_config_versions").find(query).sort([("created_at", -1)]).limit(max(1, min(int(limit or 50), 200)))
        return [serialize_doc(row) async for row in rows]

    async def export_snapshot(self) -> dict[str, Any]:
        modules = await self.get_value("modules", DEFAULT_MODULES)
        ai = await self.get_value("ai", DEFAULT_AI_CONFIG)
        trajectory = await self.get_value("trajectory_forecast", DEFAULT_TRAJECTORY_FORECAST_CONFIG)
        rules = [serialize_doc(row) async for row in self.db.col("alert_rules").find({}).sort([("category", 1), ("rule_id", 1)]).limit(1000)]
        mappings = [serialize_doc(row) async for row in self.db.col("field_mapping").find({}).sort([("standard_concept", 1), ("source_name", 1)]).limit(2000)]
        return {
            "exported_at": datetime.now(),
            "runtime_configs": {"modules": modules, "ai": ai, "trajectory_forecast": trajectory},
            "alert_rules": rules,
            "field_mappings": mappings,
        }

    async def rollback(self, key: str, version: int, *, actor: str, role: str, reason: str = "") -> dict[str, Any]:
        key = str(key or "").strip()
        if key not in {"modules", "ai", "trajectory_forecast"}:
            raise ValueError("unsupported runtime config key")
        record = await self.db.col("runtime_config_versions").find_one({"key": key, "version": int(version)})
        if not record:
            raise ValueError("version not found")
        value = deepcopy(record.get("value"))
        await self._set_config(key, value, actor=actor, role=role, reason=reason or f"rollback to version {version}", action="rollback_runtime_config")
        doc = await self.db.col("runtime_configs").find_one({"key": key})
        return {"key": key, "value": serialize_doc((doc or {}).get("value")), "rolled_back_from": int(version)}

    async def import_snapshot(self, snapshot: dict[str, Any], *, actor: str, role: str, reason: str = "") -> dict[str, Any]:
        if not isinstance(snapshot, dict):
            raise ValueError("snapshot must be object")
        runtime_configs = snapshot.get("runtime_configs") if isinstance(snapshot.get("runtime_configs"), dict) else snapshot
        imported: list[str] = []
        skipped = {"alert_rules": "v1 import validates only; use single-rule editor to avoid bulk overwrite", "field_mappings": "v1 import validates only; use single-field editor to avoid bulk overwrite"}
        for key in ("modules", "ai", "trajectory_forecast"):
            if key not in runtime_configs:
                continue
            value = deepcopy(runtime_configs[key])
            if key == "trajectory_forecast":
                current = await self.get_value("trajectory_forecast", DEFAULT_TRAJECTORY_FORECAST_CONFIG) or {}
                value = self.normalize_trajectory_forecast(value if isinstance(value, dict) else {}, current)
            elif key == "modules" and not isinstance(value, list):
                raise ValueError("modules must be list")
            elif key == "ai" and not isinstance(value, dict):
                raise ValueError("ai must be object")
            await self._set_config(key, value, actor=actor, role=role, reason=reason or "import runtime config", action="import_runtime_config")
            imported.append(key)
        return {"imported": imported, "skipped": skipped}

    async def update_modules(self, modules: list[dict[str, Any]], *, actor: str) -> dict[str, Any]:
        normalized = []
        defaults_by_key = {item["key"]: item for item in DEFAULT_MODULES}
        for item in modules:
            key = str(item.get("key") or "").strip()
            if not key:
                continue
            base = defaults_by_key.get(key, {})
            normalized.append(
                {
                    "key": key,
                    "name": str(item.get("name") or base.get("name") or key),
                    "enabled": bool(item.get("enabled", True)),
                    "description": str(item.get("description") or base.get("description") or ""),
                    "visible": bool(item.get("visible", True)),
                }
            )
        await self._set_config("modules", normalized, actor=actor)
        return {"modules": normalized}

    async def update_ai(self, payload: dict[str, Any], *, actor: str) -> dict[str, Any]:
        current = await self.get_value("ai", DEFAULT_AI_CONFIG) or {}
        value = deepcopy(DEFAULT_AI_CONFIG)
        value.update(current)
        for key in ["enabled", "fast_model", "medical_model", "fallback_model", "reasoning_model", "temperature", "max_tokens", "timeout", "routes", "providers"]:
            if key in payload:
                value[key] = payload[key]
        if isinstance(value.get("providers"), list):
            value["providers"] = [
                {
                    "id": str(item.get("id") or "").strip(),
                    "name": str(item.get("name") or item.get("id") or "").strip(),
                    "base_url": str(item.get("base_url") or "").strip(),
                    "api_key": str(item.get("api_key") or "").strip(),
                    "model": str(item.get("model") or "").strip(),
                    "purpose": str(item.get("purpose") or "fast").strip(),
                    "priority": int(item.get("priority") or 50),
                    "enabled": bool(item.get("enabled", True)),
                    "timeout": int(item.get("timeout") or value.get("timeout") or 30),
                    "temperature": float(item.get("temperature", value.get("temperature") or 0.1) or 0.1),
                    "max_tokens": int(item.get("max_tokens") or value.get("max_tokens") or 1024),
                }
                for item in value["providers"]
                if str(item.get("id") or item.get("model") or "").strip()
            ]
        if isinstance(payload.get("circuit_breaker"), dict):
            breaker = dict(value.get("circuit_breaker") or {})
            breaker.update(payload["circuit_breaker"])
            value["circuit_breaker"] = breaker
        value["enabled"] = bool(value.get("enabled", True))
        value["temperature"] = float(value.get("temperature") or 0.1)
        value["max_tokens"] = int(value.get("max_tokens") or 1024)
        value["timeout"] = int(value.get("timeout") or 30)
        await self._set_config("ai", value, actor=actor)
        return {"ai": value}

    def normalize_trajectory_forecast(self, payload: dict[str, Any], current: dict[str, Any] | None = None) -> dict[str, Any]:
        allowed = {item["code"] for item in TRAJECTORY_CODE_OPTIONS}
        current = current if isinstance(current, dict) else {}
        value = deepcopy(DEFAULT_TRAJECTORY_FORECAST_CONFIG)
        value.update(current)
        value.update({key: payload[key] for key in ("enabled", "alert_enabled", "horizon_hours", "scope", "calibration_version") if key in payload})
        default_codes = [str(code) for code in payload.get("default_codes", value.get("default_codes") or []) if str(code) in allowed]
        if not default_codes:
            default_codes = list(DEFAULT_TRAJECTORY_FORECAST_CONFIG["default_codes"])
        alert_codes = [str(code) for code in payload.get("alert_codes", value.get("alert_codes") or []) if str(code) in allowed]
        alert_codes = [code for code in alert_codes if code in set(default_codes)]
        value["default_codes"] = default_codes
        value["alert_codes"] = alert_codes
        value["enabled"] = bool(value.get("enabled", True))
        value["alert_enabled"] = bool(value.get("alert_enabled", False))
        value["horizon_hours"] = max(1, min(int(value.get("horizon_hours") or 6), 12))
        value["scope"] = str(value.get("scope") or "global")
        value["calibration_version"] = str(value.get("calibration_version") or "uncalibrated-v1")

        thresholds = []
        for item in payload.get("thresholds", value.get("thresholds") or []):
            if not isinstance(item, dict):
                continue
            code = str(item.get("code") or "").strip()
            if code not in set(alert_codes):
                continue
            operator = str(item.get("operator") or "<").strip()
            if operator not in {"<", "<=", ">", ">="}:
                operator = "<"
            try:
                threshold = float(item.get("threshold"))
                probability = float(item.get("probability"))
            except Exception:
                continue
            thresholds.append(
                {
                    "code": code,
                    "operator": operator,
                    "threshold": threshold,
                    "probability": max(0.01, min(probability, 0.99)),
                    "severity": str(item.get("severity") or "warning").strip().lower(),
                    "horizon_hours": max(1, min(int(item.get("horizon_hours") or value["horizon_hours"]), 12)),
                }
            )
        value["thresholds"] = thresholds
        return value

    async def update_trajectory_forecast(self, payload: dict[str, Any], *, actor: str) -> dict[str, Any]:
        doc = await self._get_config_doc("trajectory_forecast", DEFAULT_TRAJECTORY_FORECAST_CONFIG)
        current = doc.get("value") or {}
        expected_version = payload.get("expected_version")
        current_version = int((current or {}).get("version") or 1)
        if expected_version is not None and int(expected_version) != current_version:
            raise ValueError(f"配置已被更新，请刷新后重试（当前版本 {current_version}）")
        value = self.normalize_trajectory_forecast(payload, current)
        value["version"] = current_version + 1
        await self._set_config("trajectory_forecast", value, actor=actor)
        return {"trajectory_forecast": value, "effective_version": value["version"], "applied_at": datetime.now()}

    async def update_alert_rule(self, rule_id: str, payload: dict[str, Any], *, actor: str) -> dict[str, Any]:
        now = datetime.now()
        set_doc: dict[str, Any] = {"updated_at": now, "updated_by": actor}
        for key in ["name", "category", "parameter", "severity", "enabled"]:
            if key in payload:
                set_doc[key] = payload[key]
        if "condition" in payload and isinstance(payload["condition"], dict):
            set_doc["condition"] = payload["condition"]
        if "threshold" in payload:
            current = await self.db.col("alert_rules").find_one({"rule_id": rule_id}) or {}
            condition = dict(current.get("condition") or {})
            condition["threshold"] = payload.get("threshold")
            if payload.get("operator"):
                condition["operator"] = payload.get("operator")
            set_doc["condition"] = condition
        await self.db.col("alert_rules").update_one(
            {"rule_id": rule_id},
            {"$set": set_doc, "$setOnInsert": {"rule_id": rule_id, "created_at": now}},
            upsert=True,
        )
        doc = await self.db.col("alert_rules").find_one({"rule_id": rule_id})
        await write_audit_log(self.db, action="update_alert_rule", module="runtime_config", actor=actor, target_type="alert_rule", target_id=rule_id, detail=payload)
        return {"rule": serialize_doc(doc)}

    async def update_field_mapping(self, payload: dict[str, Any], *, actor: str) -> dict[str, Any]:
        now = datetime.now()
        source_code = str(payload.get("source_code") or "").strip()
        source_name = str(payload.get("source_name") or "").strip()
        if not source_code or not source_name:
            raise ValueError("source_code 和 source_name 必填")
        set_doc = {
            "source_code": source_code,
            "source_name": source_name,
            "standard_concept": str(payload.get("standard_concept") or "").strip(),
            "unit": str(payload.get("unit") or "").strip(),
            "module": str(payload.get("module") or "").strip(),
            "enabled": bool(payload.get("enabled", True)),
            "updated_at": now,
            "updated_by": actor,
        }
        await self.db.col("field_mapping").update_one(
            {"source_code": source_code, "source_name": source_name},
            {"$set": set_doc, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
        doc = await self.db.col("field_mapping").find_one({"source_code": source_code, "source_name": source_name})
        await write_audit_log(self.db, action="update_field_mapping", module="runtime_config", actor=actor, target_type="field_mapping", target_id=f"{source_name}:{source_code}", detail=payload)
        return {"mapping": serialize_doc(doc)}

    async def _next_version(self, key: str) -> int:
        latest = await self.db.col("runtime_config_versions").find_one({"key": key}, sort=[("version", -1)])
        return int((latest or {}).get("version") or 0) + 1

    async def _set_config(self, key: str, value: Any, *, actor: str, role: str = "admin", reason: str = "", action: str = "update_runtime_config") -> None:
        now = datetime.now()
        current = await self.db.col("runtime_configs").find_one({"key": key})
        previous_value = deepcopy((current or {}).get("value"))
        version = await self._next_version(key)
        await self.db.col("runtime_configs").update_one(
            {"key": key},
            {"$set": {"value": value, "updated_at": now, "updated_by": actor}, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
        await self.db.col("runtime_config_versions").insert_one(
            {
                "key": key,
                "version": version,
                "value": deepcopy(value),
                "previous_value": previous_value,
                "actor": actor,
                "role": role,
                "reason": reason,
                "action": action,
                "created_at": now,
                "updated_at": now,
            }
        )
        await write_audit_log(self.db, action=action, module="runtime_config", actor=actor, target_type="runtime_config", target_id=key, detail={"key": key, "version": version, "reason": reason})
