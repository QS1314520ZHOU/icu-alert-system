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
        rules = [serialize_doc(row) async for row in self.db.col("alert_rules").find({}).sort([("category", 1), ("rule_id", 1)]).limit(300)]
        mappings = [serialize_doc(row) async for row in self.db.col("field_mapping").find({}).sort([("standard_concept", 1), ("source_name", 1)]).limit(500)]
        return {
            "modules": modules_doc.get("value") or [],
            "ai": ai_doc.get("value") or {},
            "alert_rules": rules,
            "field_mappings": mappings,
            "generated_at": datetime.now(),
        }

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

    async def _set_config(self, key: str, value: Any, *, actor: str) -> None:
        now = datetime.now()
        await self.db.col("runtime_configs").update_one(
            {"key": key},
            {"$set": {"value": value, "updated_at": now, "updated_by": actor}, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
        await write_audit_log(self.db, action="update_runtime_config", module="runtime_config", actor=actor, target_type="runtime_config", target_id=key, detail={"key": key})
