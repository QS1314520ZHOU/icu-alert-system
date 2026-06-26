from __future__ import annotations

from datetime import datetime
from typing import Any

from app.data_adapters.base import StandardizedObservation
from app.utils.clinical import _cap_time, _cap_value
from app.utils.labs import _lab_time
from app.utils.parse import _parse_number


DEFAULT_CONCEPT_CODES: dict[str, list[str]] = {
    "spo2": ["param_spo2"],
    "fio2": ["param_FiO2", "param_fio2"],
    "rr": ["param_resp", "param_vent_resp", "param_HuXiPinLv"],
    "peep": ["param_vent_measure_peep", "param_vent_peep"],
    "minute_ventilation": ["param_vent_VE"],
}


class MongoClinicalDataAdapter:
    data_source = "mongo"

    def __init__(self, *, db: Any, engine: Any | None = None) -> None:
        self.db = db
        self.engine = engine

    async def _codes(self, concept: str, defaults: list[str], source_names: list[str] | None = None) -> list[str]:
        if self.engine is not None and hasattr(self.engine, "_field_mapping_codes"):
            return await self.engine._field_mapping_codes(
                module="respiratory",
                concepts=[concept],
                source_names=source_names or ["bedside", "deviceCap"],
                defaults=defaults,
            )
        return defaults

    def _pid(self, patient: dict[str, Any]) -> str:
        return str(patient.get("_id") or patient.get("patient_id") or patient.get("pid") or "").strip()

    async def get_vitals_series(self, patient: dict[str, Any], concept: str, start: datetime, end: datetime | None = None) -> list[StandardizedObservation]:
        pid = self._pid(patient)
        if not pid:
            return []
        codes = await self._codes(concept, DEFAULT_CONCEPT_CODES.get(concept, [concept]), ["bedside"])
        query: dict[str, Any] = {"pid": pid, "code": {"$in": codes}, "time": {"$gte": start}}
        if end:
            query["time"]["$lt"] = end
        rows: list[StandardizedObservation] = []
        cursor = self.db.col("bedside").find(query, {"time": 1, "code": 1, "name": 1, "strVal": 1, "intVal": 1, "fVal": 1, "value": 1}).sort("time", 1).limit(5000)
        async for doc in cursor:
            value = _cap_value(doc)
            t = _cap_time(doc)
            if value is None or not t:
                continue
            rows.append(StandardizedObservation(concept=concept, value=value, unit=self._unit(concept), timestamp=t, source="bedside", match_method="code", raw_code=str(doc.get("code") or ""), raw_name=str(doc.get("name") or "")))
        return rows

    async def get_devices(self, patient: dict[str, Any], concepts: list[str], start: datetime, end: datetime | None = None) -> list[StandardizedObservation]:
        pid = self._pid(patient)
        if not pid:
            return []
        device_id = ""
        if self.engine is not None and hasattr(self.engine, "_get_active_vent_bind"):
            bind = await self.engine._get_active_vent_bind(pid)
            device_id = str((bind or {}).get("deviceID") or "")
        if not device_id and self.engine is not None and hasattr(self.engine, "_get_device_id_for_patient"):
            device_id = str(await self.engine._get_device_id_for_patient(patient, ["vent"]) or "")
        if not device_id:
            return []
        concept_codes: dict[str, list[str]] = {}
        all_codes: list[str] = []
        for concept in concepts:
            codes = await self._codes(concept, DEFAULT_CONCEPT_CODES.get(concept, [concept]), ["deviceCap"])
            concept_codes[concept] = codes
            all_codes.extend(codes)
        query: dict[str, Any] = {"deviceID": device_id, "code": {"$in": list(dict.fromkeys(all_codes))}, "time": {"$gte": start}}
        if end:
            query["time"]["$lt"] = end
        rows: list[StandardizedObservation] = []
        cursor = self.db.col("deviceCap").find(query, {"time": 1, "code": 1, "name": 1, "strVal": 1, "intVal": 1, "fVal": 1, "value": 1}).sort("time", 1).limit(5000)
        async for doc in cursor:
            value = _cap_value(doc)
            t = _cap_time(doc)
            code = str(doc.get("code") or "")
            if value is None or not t:
                continue
            concept = next((key for key, codes in concept_codes.items() if code in codes), code)
            rows.append(StandardizedObservation(concept=concept, value=value, unit=self._unit(concept), timestamp=t, source="deviceCap", match_method="code", raw_code=code, raw_name=str(doc.get("name") or "")))
        return rows

    async def get_labs(self, patient: dict[str, Any], concepts: list[str], start: datetime, end: datetime | None = None) -> list[StandardizedObservation]:
        his_pid = str(patient.get("hisPid") or patient.get("hisPID") or "").strip()
        if not his_pid:
            return []
        rows: list[StandardizedObservation] = []
        cursor = self.db.dc_col("VI_ICU_EXAM_ITEM").find({"hisPid": his_pid}).sort("authTime", -1).limit(4000)
        async for doc in cursor:
            t = _lab_time(doc)
            if not t or t < start or (end and t >= end):
                continue
            name = str(doc.get("itemCnName") or doc.get("itemName") or doc.get("itemCode") or "")
            code = str(doc.get("itemCode") or "")
            blob = f"{code} {name}".lower()
            concept = next((item for item in concepts if item.lower() in blob), "")
            if not concept:
                continue
            value = _parse_number(doc.get("result") or doc.get("resultValue") or doc.get("value"))
            if value is None:
                continue
            rows.append(StandardizedObservation(concept=concept, value=value, unit=str(doc.get("unit") or doc.get("resultUnit") or ""), timestamp=t, source="VI_ICU_EXAM_ITEM", match_method="code" if code else "keyword", raw_code=code, raw_name=name))
        rows.sort(key=lambda item: item.timestamp or datetime.min)
        return rows

    async def get_drug_exposure(self, patient: dict[str, Any], start: datetime, end: datetime | None = None) -> list[StandardizedObservation]:
        pid = self._pid(patient)
        if not pid:
            return []
        query: dict[str, Any] = {"pid": pid}
        rows: list[StandardizedObservation] = []
        cursor = self.db.col("drugExe").find(query).sort("time", -1).limit(3000)
        async for doc in cursor:
            t = _cap_time(doc) or doc.get("executeTime") or doc.get("startTime")
            if not isinstance(t, datetime) or t < start or (end and t >= end):
                continue
            name = str(doc.get("drugName") or doc.get("name") or doc.get("orderName") or "")
            code = str(doc.get("drugCode") or doc.get("orderCode") or "")
            rows.append(StandardizedObservation(concept="drug_exposure", value=name, unit="", timestamp=t, source="drugExe", match_method="code" if code else "keyword", raw_code=code, raw_name=name))
        rows.sort(key=lambda item: item.timestamp or datetime.min)
        return rows

    def _unit(self, concept: str) -> str:
        return {"spo2": "%", "fio2": "fraction", "rr": "/min", "peep": "cmH2O", "minute_ventilation": "L/min"}.get(concept, "")
