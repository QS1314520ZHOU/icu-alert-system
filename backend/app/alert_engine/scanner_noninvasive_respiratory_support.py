from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from .scanners import BaseScanner, ScannerSpec


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except Exception:
        return None


def _fio2_fraction(value: Any) -> float | None:
    fio2 = _to_float(value)
    if fio2 is None:
        return None
    return fio2 / 100.0 if fio2 > 1 else fio2


class NoninvasiveRespiratorySupportScanner(BaseScanner):
    """HFNC/NIV 失败风险监测：ROX 与 HACOR 首版规则化实现。"""

    def __init__(self, engine) -> None:
        super().__init__(
            engine,
            ScannerSpec(
                name="noninvasive_respiratory_support",
                interval_key="noninvasive_respiratory_support",
                default_interval=900,
                initial_delay=83,
            ),
        )

    def _cfg(self) -> dict[str, Any]:
        cfg = self.engine._cfg("alert_engine", "noninvasive_respiratory_support", default={}) if hasattr(self.engine, "_cfg") else {}
        return cfg if isinstance(cfg, dict) else {}

    async def scan(self) -> None:
        cfg = self._cfg()
        suppression = self.engine.config.yaml_cfg.get("alert_engine", {}).get("suppression", {})
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))
        now = datetime.now()
        cursor = self.engine.db.col("patient").find(
            self.engine._active_patient_query(),
            {"_id": 1, "name": 1, "hisPid": 1, "hisBed": 1, "dept": 1, "hisDept": 1, "age": 1, "hisAge": 1},
        )
        patients = [row async for row in cursor]
        triggered = 0
        for patient_doc in patients:
            patient_id = patient_doc.get("_id")
            if not patient_id:
                continue
            support = await self._detect_support(str(patient_id), now, cfg)
            if not support:
                continue
            if support["type"] == "HFNC":
                alert = await self._scan_hfnc(patient_doc, support, now, same_rule_sec, max_per_hour, cfg)
            else:
                alert = await self._scan_niv(patient_doc, support, now, same_rule_sec, max_per_hour, cfg)
            if alert:
                triggered += 1
        if triggered:
            self.engine._log_info("HFNC/NIV风险", triggered)

    async def _detect_support(self, patient_id: str, now: datetime, cfg: dict[str, Any]) -> dict[str, Any] | None:
        bind = await self._latest_support_bind(patient_id)
        bind_text = self._bind_text(bind or {})
        support_type = None
        if self._contains_any(bind_text, cfg.get("hfnc_keywords", ["hfnc", "高流量", "高流量鼻导管", "high flow"])):
            support_type = "HFNC"
        elif self._contains_any(bind_text, cfg.get("niv_keywords", ["niv", "无创", "bipap", "cpap", "noninvasive"])):
            support_type = "NIV"

        code_map = await self._support_code_map()
        codes = list(dict.fromkeys([code for values in code_map.values() for code in values]))
        snapshot = await self.engine._get_latest_param_snapshot_by_pid(
            patient_id,
            codes=codes,
            lookback_minutes=int(cfg.get("lookback_minutes", 120)),
            limit=1000,
        )
        params = snapshot.get("params") if isinstance(snapshot, dict) else {}
        fio2 = self._first(params, code_map["fio2"])
        flow = self._first(params, code_map["hfnc_flow"])
        if support_type is None:
            if flow is not None and flow >= float(cfg.get("hfnc_flow_threshold_l_min", 30)):
                support_type = "HFNC"
            elif self._first(params, code_map["niv_ipap"] + code_map["niv_epap"]) is not None:
                support_type = "NIV"
        if support_type is None:
            return None
        return {
            "type": support_type,
            "bind": bind,
            "bind_text": bind_text,
            "params": params,
            "snapshot_time": snapshot.get("time") if isinstance(snapshot, dict) else now,
            "fio2": fio2,
            "flow_l_min": flow,
            "ipap": self._first(params, code_map["niv_ipap"]),
            "epap": self._first(params, code_map["niv_epap"]),
            "leak": self._first(params, code_map["niv_leak"]),
            "code_map": code_map,
        }

    async def _latest_support_bind(self, patient_id: str) -> dict[str, Any] | None:
        cursor = self.engine.db.col("deviceBind").find(
            {"pid": str(patient_id), "unBindTime": None},
            {"type": 1, "deviceName": 1, "deviceType": 1, "deviceID": 1, "bindTime": 1},
        ).sort("bindTime", -1).limit(20)
        async for doc in cursor:
            text = self._bind_text(doc)
            if any(token in text for token in ("hfnc", "高流量", "无创", "niv", "bipap", "cpap", "high flow")):
                return doc
        return None

    async def _scan_hfnc(
        self,
        patient_doc: dict[str, Any],
        support: dict[str, Any],
        now: datetime,
        same_rule_sec: int,
        max_per_hour: int,
        cfg: dict[str, Any],
    ) -> dict[str, Any] | None:
        patient_id = str(patient_doc.get("_id"))
        params = support.get("params") or {}
        code_map = support.get("code_map") or {}
        spo2 = self._first(params, code_map.get("spo2") or ["param_spo2"])
        rr = self._first(params, code_map.get("rr_measured") or ["param_resp", "param_HuXiPinLv"])
        fio2_frac = _fio2_fraction(support.get("fio2"))
        if spo2 is None or rr is None or rr <= 0 or fio2_frac is None or fio2_frac <= 0:
            return None
        rox = round((float(spo2) / fio2_frac) / float(rr), 2)
        threshold = float(cfg.get("rox_failure_threshold", 4.88))
        severe_threshold = float(cfg.get("rox_critical_threshold", 3.85))
        if rox >= threshold:
            return None
        rule_id = "HFNC_FAILURE_RISK"
        if await self.engine._is_suppressed(patient_id, rule_id, same_rule_sec, max_per_hour):
            return None
        severity = "critical" if rox < severe_threshold else "high"
        return await self.engine._create_alert(
            rule_id=rule_id,
            name="HFNC 失败风险升高",
            category="ventilator",
            alert_type="hfnc_failure_risk",
            severity=severity,
            parameter="rox_index",
            condition={"operator": "<", "threshold": threshold},
            value=rox,
            patient_id=patient_id,
            patient_doc=patient_doc,
            device_id=(support.get("bind") or {}).get("deviceID"),
            source_time=support.get("snapshot_time") or now,
            explanation={
                "summary": f"当前 ROX 指数 {rox}，提示 HFNC 失败/延误插管风险升高。",
                "evidence": [f"SpO2 {spo2}%", f"FiO2 {round(fio2_frac, 2)}", f"RR {rr}/min", f"Flow {support.get('flow_l_min')} L/min"],
                "suggestion": "建议 1-2 小时内复评 ROX、呼吸功和血气；若持续下降或循环/意识恶化，及时讨论气管插管。",
                "text": "",
            },
            extra={"support": support, "rox_index": rox, "threshold": threshold},
        )

    async def _scan_niv(
        self,
        patient_doc: dict[str, Any],
        support: dict[str, Any],
        now: datetime,
        same_rule_sec: int,
        max_per_hour: int,
        cfg: dict[str, Any],
    ) -> dict[str, Any] | None:
        patient_id = str(patient_doc.get("_id"))
        params = support.get("params") or {}
        code_map = support.get("code_map") or {}
        spo2 = self._first(params, code_map.get("spo2") or ["param_spo2"])
        rr = self._first(params, code_map.get("rr_measured") or ["param_resp", "param_HuXiPinLv"])
        fio2_frac = _fio2_fraction(support.get("fio2"))
        labs = await self.engine._get_latest_labs_map(patient_doc.get("hisPid"), lookback_hours=6) if patient_doc.get("hisPid") else {}
        ph = _to_float(((labs.get("ph") or {}).get("value")) if isinstance(labs.get("ph"), dict) else None)
        gcs = await self.engine._get_latest_assessment(patient_id, "gcs") if hasattr(self.engine, "_get_latest_assessment") else None
        age = self._patient_age_years(patient_doc)
        hacor = self._hacor_score(spo2=spo2, fio2=fio2_frac, rr=rr, ph=ph, gcs=gcs, age=age)
        if hacor is None:
            return None
        threshold = float(cfg.get("hacor_failure_threshold", 5))
        if hacor < threshold:
            return None
        rule_id = "NIV_FAILURE_RISK"
        if await self.engine._is_suppressed(patient_id, rule_id, same_rule_sec, max_per_hour):
            return None
        severity = "critical" if hacor >= float(cfg.get("hacor_critical_threshold", 8)) else "high"
        return await self.engine._create_alert(
            rule_id=rule_id,
            name="NIV 失败风险升高",
            category="ventilator",
            alert_type="niv_failure_risk",
            severity=severity,
            parameter="hacor_score",
            condition={"operator": ">=", "threshold": threshold},
            value=hacor,
            patient_id=patient_id,
            patient_doc=patient_doc,
            device_id=(support.get("bind") or {}).get("deviceID"),
            source_time=support.get("snapshot_time") or now,
            explanation={
                "summary": f"当前 HACOR 估算 {hacor} 分，提示 NIV 失败风险升高。",
                "evidence": [f"SpO2 {spo2}%", f"FiO2 {fio2_frac}", f"RR {rr}/min", f"pH {ph}", f"GCS {gcs}", f"Age {age}"],
                "suggestion": "建议尽快复评 NIV 适应证、漏气和同步性；若氧合/酸中毒/意识恶化，不应延误气管插管。",
                "text": "",
            },
            extra={"support": support, "hacor_score": hacor, "ph": ph, "gcs": gcs, "age": age},
        )

    def _hacor_score(
        self,
        *,
        spo2: float | None,
        fio2: float | None,
        rr: float | None,
        ph: float | None,
        gcs: float | None,
        age: float | None,
    ) -> int | None:
        if spo2 is None or fio2 is None or fio2 <= 0 or rr is None:
            return None
        sf = float(spo2) / float(fio2)
        score = 0
        if ph is not None:
            if ph < 7.25:
                score += 4
            elif ph < 7.30:
                score += 3
            elif ph < 7.35:
                score += 2
        if gcs is not None and gcs < 15:
            score += 2 if gcs >= 11 else 5
        if rr >= 35:
            score += 3
        elif rr >= 30:
            score += 2
        elif rr >= 25:
            score += 1
        if sf < 100:
            score += 6
        elif sf < 150:
            score += 4
        elif sf < 200:
            score += 2
        if age is not None and age >= 75:
            score += 2
        elif age is not None and age >= 65:
            score += 1
        return int(score)

    def _first(self, params: dict[str, Any], keys: list[str]) -> float | None:
        for key in keys:
            value = _to_float(params.get(key))
            if value is not None:
                return value
        return None

    async def _support_code_map(self) -> dict[str, list[str]]:
        defaults = {
            "spo2": ["param_spo2"],
            "rr_measured": ["param_resp", "param_HuXiPinLv"],
            "fio2": ["param_FiO2", "param_fio2"],
            "hfnc_flow": ["param_hfnc_flow", "param_oxygen_flow"],
            "niv_ipap": ["param_niv_ipap"],
            "niv_epap": ["param_niv_epap"],
            "niv_leak": ["param_niv_leak"],
        }
        out: dict[str, list[str]] = {}
        for concept, fallback in defaults.items():
            if hasattr(self.engine, "_field_mapping_codes"):
                out[concept] = await self.engine._field_mapping_codes(
                    module="respiratory",
                    concepts=[concept],
                    source_names=["bedside", "deviceCap"],
                    defaults=fallback,
                )
            else:
                out[concept] = fallback
        return out

    def _bind_text(self, doc: dict[str, Any]) -> str:
        return " ".join(str(doc.get(key) or "") for key in ("type", "deviceName", "deviceType")).lower()

    def _contains_any(self, text: str, keywords: list[str]) -> bool:
        lowered = str(text or "").lower()
        return any(str(keyword).lower() in lowered for keyword in keywords if str(keyword).strip())

    def _patient_age_years(self, patient_doc: dict[str, Any]) -> float | None:
        for key in ("age", "hisAge"):
            value = patient_doc.get(key)
            if value is None:
                continue
            parsed = _to_float(value)
            if parsed is not None:
                return parsed
        return None
