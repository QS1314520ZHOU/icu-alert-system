"""院感预防 bundle 监测。"""
from __future__ import annotations

from datetime import datetime, timedelta

from app.utils.labs import _lab_time
from app.utils.parse import _parse_number


class HaiBundleMonitorMixin:
    def _hai_cfg(self) -> dict:
        cfg = self._cfg("alert_engine", "hai_bundle", default={}) or {}
        return cfg if isinstance(cfg, dict) else {}

    async def _hai_insert_time(self, pid, keywords: list[str], hours: int = 24 * 30) -> datetime | None:
        if hasattr(self, "_infer_device_insert_time"):
            return await self._infer_device_insert_time(pid, keywords, hours=hours)
        events = await self._get_recent_text_events(pid, keywords, hours=hours, limit=2000)
        times = [x.get("time") for x in events if isinstance(x.get("time"), datetime)]
        return min(times) if times else None

    async def _latest_temp_value(self, pid) -> float | None:
        code = str(self._cfg("vital_signs", "temperature", "code", default="param_T"))
        snap = await self._get_latest_param_snapshot_by_pid(pid, codes=[code])
        if not snap:
            return None
        return (snap.get("params") or {}).get(code)

    async def _has_recent_bedside_keyword(self, pid, keywords: list[str], hours: int = 24) -> bool:
        rows = await self._get_recent_text_events(pid, keywords, hours=hours, limit=400)
        return bool(rows)

    async def _latest_positive_culture(self, his_pid: str | None, keywords: list[str], hours: int = 72) -> dict | None:
        if not his_pid:
            return None
        since = datetime.now() - timedelta(hours=max(hours, 1))
        positive_keywords = ["阳性", "positive", "生长", "检出", "分离出"]
        cursor = self.db.dc_col("VI_ICU_EXAM_ITEM").find({"hisPid": his_pid}).sort("authTime", -1).limit(2000)
        for doc in [d async for d in cursor]:
            t = _lab_time(doc)
            if not t or t < since:
                continue
            name = " ".join(str(doc.get(k) or "") for k in ("itemCnName", "itemName", "itemCode")).lower()
            if not any(str(k).lower() in name for k in keywords):
                continue
            result = str(doc.get("result") or doc.get("resultValue") or "").lower()
            if any(k in result for k in positive_keywords):
                return {"time": t, "name": name, "result": result}
        return None

    async def _has_abnormal_urine(self, his_pid: str | None, hours: int = 72) -> bool:
        if not his_pid:
            return False
        since = datetime.now() - timedelta(hours=max(hours, 1))
        keywords = ["尿白细胞", "白细胞酯酶", "亚硝酸盐", "细菌", "尿培养", "尿常规"]
        abnormal_keywords = ["阳性", "异常", "positive", "+", "检出", "增高"]
        cursor = self.db.dc_col("VI_ICU_EXAM_ITEM").find({"hisPid": his_pid}).sort("authTime", -1).limit(1000)
        async for doc in cursor:
            t = _lab_time(doc)
            if not t or t < since:
                continue
            name = " ".join(str(doc.get(k) or "") for k in ("itemCnName", "itemName", "itemCode")).lower()
            if not any(k in name for k in keywords):
                continue
            result = str(doc.get("result") or doc.get("resultValue") or "").lower()
            if any(k in result for k in abnormal_keywords):
                return True
            num = _parse_number(doc.get("result") or doc.get("resultValue"))
            if num is not None and num > 0:
                return True
        return False

    async def _ventilation_start_time(self, patient_doc: dict) -> datetime | None:
        pid = patient_doc.get("_id")
        pid_str = str(pid) if pid is not None else ""
        if pid_str:
            bind = await self.db.col("deviceBind").find_one(
                {"pid": pid_str, "unBindTime": None, "type": {"$in": ["vent", "Vent", "ventilator", "呼吸机"]}},
                {"bindTime": 1},
                sort=[("bindTime", 1)],
            )
            if bind and isinstance(bind.get("bindTime"), datetime):
                return bind.get("bindTime")
        return await self._hai_insert_time(pid, self._hai_cfg().get("vent_keywords", ["气管插管", "ett", "endotracheal", "机械通气"]))

    async def scan_hai_bundle(self) -> None:
        from .scanner_hai_bundle import HaiBundleScanner

        await HaiBundleScanner(self).scan()
