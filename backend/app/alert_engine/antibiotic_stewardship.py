"""抗菌药物管理（Antibiotic Stewardship）"""
from __future__ import annotations

import re
import time
from datetime import datetime, timedelta
from typing import Any


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _hours_between(a: datetime | None, b: datetime | None) -> float:
    if not a or not b:
        return 0.0
    return max(0.0, (b - a).total_seconds() / 3600.0)


class AntibioticStewardshipMixin:
    def _ensure_abx_runtime_state(self) -> None:
        if not hasattr(self, "_abx_dictionary_cache"):
            self._abx_dictionary_cache = {
                "expires_at": 0.0,
                "antibiotic_names": [],
                "broad_spectrum_names": [],
            }

    def _get_rule_cfg_list(self, key: str, default: list[str]) -> list[str]:
        return self._get_cfg_list(("alert_engine", "antibiotic_stewardship", key), default)

    def _text_has_any(self, text: str, keywords: list[str]) -> bool:
        t = str(text or "").lower()
        return any(str(k).lower() in t for k in keywords if str(k).strip())

    def _event_time(self, doc: dict) -> datetime | None:
        return (
            _parse_dt(doc.get("executeTime"))
            or _parse_dt(doc.get("startTime"))
            or _parse_dt(doc.get("orderTime"))
        )

    async def _load_antibiotic_dictionary(self) -> tuple[list[str], list[str]]:
        self._ensure_abx_runtime_state()
        now_ts = time.time()
        cached = self._abx_dictionary_cache
        if cached.get("expires_at", 0.0) > now_ts:
            return cached.get("antibiotic_names", []), cached.get("broad_spectrum_names", [])

        abx_names: set[str] = set()
        broad_names: set[str] = set()

        antibiotic_type_keywords = self._get_rule_cfg_list(
            "antibiotic_type_keywords",
            ["抗生素", "抗菌", "抗感染", "antibiotic", "antimicrobial"],
        )
        broad_type_keywords = self._get_rule_cfg_list(
            "broad_type_keywords",
            ["广谱", "碳青霉烯", "三四代头孢", "高级别", "broad", "carbapenem"],
        )
        broad_name_keywords = self._get_rule_cfg_list(
            "broad_spectrum_keywords",
            ["美罗培南", "亚胺培南", "哌拉西林他唑巴坦", "头孢哌酮舒巴坦", "头孢吡肟", "替加环素"],
        )
        seeded_abx_keywords = self._get_rule_cfg_list(
            "antibiotic_keywords",
            ["万古霉素", "头孢", "青霉素", "美罗培南", "阿奇霉素", "左氧氟沙星", "替考拉宁"],
        )

        # 从 configDrug 自动识别抗生素词典
        try:
            cursor = self.db.col("configDrug").find(
                {},
                {
                    "name": 1, "drugName": 1, "genericName": 1, "tradeName": 1, "fullName": 1,
                    "drugType": 1, "category": 1, "classify": 1, "classifyName": 1, "tags": 1,
                },
            )
            async for doc in cursor:
                name = str(
                    doc.get("name")
                    or doc.get("drugName")
                    or doc.get("genericName")
                    or doc.get("tradeName")
                    or doc.get("fullName")
                    or ""
                ).strip()
                if not name:
                    continue
                type_text = " ".join(
                    str(doc.get(k) or "")
                    for k in ("drugType", "category", "classify", "classifyName", "tags")
                )
                if self._text_has_any(type_text, antibiotic_type_keywords):
                    abx_names.add(name)
                    if self._text_has_any(type_text, broad_type_keywords):
                        broad_names.add(name)
        except Exception:
            pass

        for kw in seeded_abx_keywords:
            if str(kw).strip():
                abx_names.add(str(kw).strip())
        for kw in broad_name_keywords:
            if str(kw).strip():
                broad_names.add(str(kw).strip())

        abx_list = sorted(abx_names)
        broad_list = sorted(broad_names)
        cached["antibiotic_names"] = abx_list
        cached["broad_spectrum_names"] = broad_list
        cached["expires_at"] = now_ts + 3600
        return abx_list, broad_list

    def _match_name_keywords(self, name: str, keywords: list[str]) -> bool:
        n = str(name or "").strip().lower()
        if not n:
            return False
        return any(str(k).strip().lower() in n for k in keywords if str(k).strip())

    def _extract_drug_name(self, doc: dict) -> str:
        return str(doc.get("drugName") or doc.get("orderName") or doc.get("drugSpec") or "").strip()

    async def _get_drug_events(self, pid_str: str, since: datetime) -> list[dict]:
        cursor = self.db.col("drugExe").find(
            {"pid": pid_str},
            {
                "executeTime": 1, "startTime": 1, "orderTime": 1,
                "drugName": 1, "orderName": 1, "drugSpec": 1,
                "route": 1, "routeName": 1, "orderType": 1,
            },
        ).sort("executeTime", -1).limit(3000)

        items: list[dict] = []
        async for doc in cursor:
            t = self._event_time(doc)
            if not t or t < since:
                continue
            name = self._extract_drug_name(doc)
            if not name:
                continue
            items.append({"time": t, "name": name, "doc": doc})
        items.sort(key=lambda x: x["time"])
        return items

    def _continuous_course(self, events: list[dict], now: datetime, max_gap_hours: float = 36.0) -> dict | None:
        if not events:
            return None
        times = sorted([e["time"] for e in events if isinstance(e.get("time"), datetime)])
        if not times:
            return None
        last_t = times[-1]
        # 近24h无执行视为疗程已结束
        if _hours_between(last_t, now) > 24:
            return None
        start_t = last_t
        prev = last_t
        for t in reversed(times[:-1]):
            if _hours_between(t, prev) <= max_gap_hours:
                start_t = t
                prev = t
            else:
                break
        return {
            "start": start_t,
            "last": last_t,
            "duration_hours": round(_hours_between(start_t, now), 2),
        }

    async def _get_culture_records(self, his_pid: str, since: datetime) -> list[dict]:
        if not his_pid:
            return []
        culture_keywords = self._get_rule_cfg_list(
            "culture_keywords",
            ["培养", "culture", "菌", "药敏", "blood culture", "sputum culture", "urine culture"],
        )
        pending_keywords = self._get_rule_cfg_list(
            "culture_pending_keywords",
            ["待报", "待回", "进行中", "pending", "preliminary", "未出"],
        )
        positive_keywords = self._get_rule_cfg_list(
            "culture_positive_keywords",
            ["阳性", "positive", "生长", "检出", "分离出", "susceptible", "resistant"],
        )

        cursor = self.db.dc_col("VI_ICU_EXAM_ITEM").find({"hisPid": his_pid}).sort("authTime", -1).limit(3000)
        records: list[dict] = []
        async for doc in cursor:
            t = (
                _parse_dt(doc.get("authTime"))
                or _parse_dt(doc.get("collectTime"))
                or _parse_dt(doc.get("reportTime"))
                or _parse_dt(doc.get("time"))
            )
            if not t or t < since:
                continue
            name = str(doc.get("itemCnName") or doc.get("itemName") or doc.get("itemCode") or "").strip()
            if not self._match_name_keywords(name, culture_keywords):
                continue
            result = str(doc.get("result") or doc.get("resultValue") or "").strip()
            flag = str(doc.get("resultFlag") or doc.get("seriousFlag") or "").strip()
            text = f"{result} {flag}".strip()
            is_final = bool(text) and (not self._match_name_keywords(text, pending_keywords))
            is_positive = bool(text) and self._match_name_keywords(text, positive_keywords)
            records.append(
                {
                    "time": t,
                    "name": name,
                    "result": result,
                    "flag": flag,
                    "is_final": is_final,
                    "is_positive": is_positive,
                }
            )
        records.sort(key=lambda x: x["time"])
        return records

    async def _has_tdm_result(self, his_pid: str, since: datetime, keywords: list[str]) -> bool:
        if not his_pid or not keywords:
            return False
        cursor = self.db.dc_col("VI_ICU_EXAM_ITEM").find({"hisPid": his_pid}).sort("authTime", -1).limit(2000)
        for doc in [d async for d in cursor]:
            t = (
                _parse_dt(doc.get("authTime"))
                or _parse_dt(doc.get("collectTime"))
                or _parse_dt(doc.get("reportTime"))
                or _parse_dt(doc.get("time"))
            )
            if not t or t < since:
                continue
            name = str(doc.get("itemCnName") or doc.get("itemName") or doc.get("itemCode") or "").strip()
            if not self._match_name_keywords(name, keywords):
                continue
            rv = str(doc.get("result") or doc.get("resultValue") or "").strip()
            if rv:
                return True
        return False

    async def scan_antibiotic_stewardship(self) -> None:
        from .scanner_antibiotic_stewardship import AntibioticStewardshipScanner

        await AntibioticStewardshipScanner(self).scan()
