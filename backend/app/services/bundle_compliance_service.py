"""Bundle 合规评分服务：组装散点能力为 ABCDEF / VAP / CLABSI / CAUTI 每日核查与合规评分。

优化策略：批量查询 + 内存分组，避免逐患者逐条目逐集合查询（N×M×K → M×K）。
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

API_TZ = ZoneInfo("Asia/Shanghai")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if value is None:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _as_api_tz(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=API_TZ)
    return value.astimezone(API_TZ)


def _hours_since(dt: datetime | None) -> float | None:
    if dt is None:
        return None
    return round((datetime.now(API_TZ) - _as_api_tz(dt)).total_seconds() / 3600.0, 1)


def _tone_from_hours(hours: float | None, green_h: float, yellow_h: float) -> str:
    if hours is None:
        return "red"
    if hours <= green_h:
        return "green"
    if hours <= yellow_h:
        return "yellow"
    return "red"


def _tone_from_rate(rate: float) -> str:
    if rate >= 80:
        return "green"
    if rate >= 60:
        return "yellow"
    return "red"


# ---------------------------------------------------------------------------
# Bundle 条目定义
# ---------------------------------------------------------------------------

BUNDLE_DEFINITIONS: dict[str, dict[str, Any]] = {
    "abcdef": {
        "name": "ABCDEF 解放束",
        "items": {
            "A": {"name": "镇痛评估(CPOT/BPS)", "green_h": 4, "yellow_h": 6, "codes": ["param_score_cpot", "param_score_bps"]},
            "B": {"name": "呼吸/SAT/SBT", "green_h": 24, "yellow_h": 36, "keywords_sat": ["sat", "唤醒试验", "停镇静", "镇静中断"], "keywords_sbt": ["sbt", "自主呼吸", "撤机"]},
            "C": {"name": "意识/镇静(RASS)", "green_h": 4, "yellow_h": 6, "codes": ["param_score_rass_obs"]},
            "D": {"name": "谵妄评估(CAM-ICU)", "green_h": 8, "yellow_h": 12, "codes": ["param_delirium_score"]},
            "E": {"name": "早期活动", "green_h": 24, "yellow_h": 36, "keywords": ["早期活动", "下床", "站立", "行走", "康复", "活动", "坐起", "床边活动"]},
            "F": {"name": "家属参与", "green_h": 24, "yellow_h": 48, "keywords": ["家属沟通", "家属告知", "沟通记录", "家属参与", "探视"]},
        },
    },
    "vap": {
        "name": "VAP 预防束",
        "items": {
            "hob": {"name": "床头抬高≥30°", "green_h": 4, "yellow_h": 6, "type": "bed_angle", "keywords": ["床头抬高", "抬高床头", "半卧位", "30°", "45°"]},
            "oral_care": {"name": "口腔护理q4h", "green_h": 4, "yellow_h": 6, "keywords": ["口腔护理", "口护", "口腔清洁", "oral_care", "oral care"]},
            "subglottic": {"name": "声门下吸引", "green_h": 8, "yellow_h": 12, "keywords": ["声门下", "吸引", "subglottic"]},
            "sat": {"name": "镇静中断(SAT)", "green_h": 24, "yellow_h": 36, "keywords": ["镇静中断", "自主清醒", "SAT", "停镇静", "暂停镇静"]},
            "stress_ulcer": {"name": "消化道溃疡预防", "green_h": 48, "yellow_h": 72, "type": "drug", "keywords": ["奥美拉唑", "泮托拉唑", "兰索拉唑", "雷贝拉唑", "法莫替丁", "雷尼替丁", "PPI", "H2RA"]},
        },
    },
    "clabsi": {
        "name": "CLABSI 预防束",
        "items": {
            "cvc_review": {"name": "CVC必要性评估", "green_h": 168, "yellow_h": 192, "keywords": ["CVC必要", "中心静脉", "深静脉", "导管必要", "置管评估"]},
            "dressing": {"name": "敷料评估", "green_h": 24, "yellow_h": 36, "keywords": ["敷料", "换药", "穿刺点", "贴膜"]},
        },
    },
    "cauti": {
        "name": "CAUTI 预防束",
        "items": {
            "foley_review": {"name": "尿管必要性", "green_h": 24, "yellow_h": 36, "keywords": ["尿管必要", "导尿管评估", "尿管评估", "foley"]},
            "perineal": {"name": "尿道口护理", "green_h": 24, "yellow_h": 36, "keywords": ["尿道口护理", "会阴护理", "尿管护理"]},
        },
    },
}


class BundleComplianceService:
    def __init__(self, db, config=None) -> None:
        self.db = db
        self.config = config

    # ------------------------------------------------------------------
    # 批量查询层：每个集合查一次，按 patient_id 分组
    # ------------------------------------------------------------------

    async def _batch_query_nurse_records(self, pids: list[str], keywords: list[str], since: datetime) -> dict[str, datetime]:
        """批量查询 nurseRecords，返回 {patient_id: latest_time}。"""
        result: dict[str, datetime] = {}
        regex = "|".join(re.escape(k) for k in keywords if k)
        if not regex or not pids:
            return result
        text_cond = {"$or": [
            {"content": {"$regex": regex, "$options": "i"}},
            {"recordTitle": {"$regex": regex, "$options": "i"}},
            {"title": {"$regex": regex, "$options": "i"}},
            {"careType": {"$regex": regex, "$options": "i"}},
            {"name": {"$regex": regex, "$options": "i"}},
        ]}
        pid_cond = {"$or": [{"pid": {"$in": pids}}, {"patient_id": {"$in": pids}}]}
        query = {"$and": [pid_cond, {"time": {"$gte": since}}, text_cond]}
        for col_name in ("nurseRecords", "nursing_record"):
            try:
                cursor = self.db.col(col_name).find(query, {"pid": 1, "patient_id": 1, "recordTime": 1, "time": 1, "created_at": 1}).sort("time", -1).limit(2000)
                async for row in cursor:
                    pid = _text(row.get("pid") or row.get("patient_id"))
                    t = _dt(row.get("recordTime") or row.get("time") or row.get("created_at"))
                    if pid and t and (pid not in result or t > result[pid]):
                        result[pid] = t
            except Exception:
                continue
        return result

    async def _batch_query_bedside(self, pids: list[str], codes: list[str], since: datetime) -> dict[str, datetime]:
        """批量查询 bedside 评分，返回 {patient_id: latest_time}。"""
        result: dict[str, datetime] = {}
        regex = "|".join(re.escape(c) for c in codes if c)
        if not regex or not pids:
            return result
        try:
            cursor = self.db.col("bedside").find(
                {"pid": {"$in": pids}, "time": {"$gte": since}, "code": {"$regex": regex, "$options": "i"}},
                {"pid": 1, "time": 1},
            ).sort("time", -1).limit(2000)
            async for row in cursor:
                pid = _text(row.get("pid"))
                t = _dt(row.get("time"))
                if pid and t and (pid not in result or t > result[pid]):
                    result[pid] = t
        except Exception:
            pass
        return result

    async def _batch_query_bed_angle(self, pids: list[str], since: datetime, threshold: float = 30) -> dict[str, datetime]:
        """批量查询 bed_angle ≥ threshold，返回 {patient_id: latest_time}。"""
        result: dict[str, datetime] = {}
        if not pids:
            return result
        try:
            cursor = self.db.col("bedside").find(
                {"pid": {"$in": pids}, "time": {"$gte": since}, "$or": [{"code": "param_bed_angle"}, {"paramCode": "param_bed_angle"}, {"name": {"$regex": "床头|床角度|bed_angle", "$options": "i"}}]},
                {"pid": 1, "time": 1, "fVal": 1, "intVal": 1, "strVal": 1, "value": 1},
            ).sort("time", -1).limit(2000)
            async for row in cursor:
                pid = _text(row.get("pid"))
                t = _dt(row.get("time"))
                if not pid or not t:
                    continue
                val = None
                for field in ("fVal", "intVal", "strVal", "value"):
                    try:
                        val = float(str(row.get(field)).replace("°", ""))
                        break
                    except Exception:
                        pass
                if val is not None and val >= threshold and (pid not in result or t > result[pid]):
                    result[pid] = t
        except Exception:
            pass
        return result

    async def _batch_query_drug(self, pids: list[str], keywords: list[str], since: datetime) -> dict[str, datetime]:
        """批量查询 drugExe，返回 {patient_id: latest_time}。"""
        result: dict[str, datetime] = {}
        regex = "|".join(re.escape(k) for k in keywords if k)
        if not regex or not pids:
            return result
        pid_cond = {"$or": [{"pid": {"$in": pids}}, {"patient_id": {"$in": pids}}]}
        time_cond = {"$or": [{"exeTime": {"$gte": since}}, {"executeTime": {"$gte": since}}, {"time": {"$gte": since}}]}
        name_cond = {"$or": [{"drugName": {"$regex": regex, "$options": "i"}}, {"orderName": {"$regex": regex, "$options": "i"}}, {"name": {"$regex": regex, "$options": "i"}}]}
        query = {"$and": [pid_cond, time_cond, name_cond]}
        try:
            cursor = self.db.col("drugExe").find(query, {"pid": 1, "patient_id": 1, "exeTime": 1, "executeTime": 1, "time": 1}).sort("exeTime", -1).limit(2000)
            async for row in cursor:
                pid = _text(row.get("pid") or row.get("patient_id"))
                t = _dt(row.get("exeTime") or row.get("executeTime") or row.get("time"))
                if pid and t and (pid not in result or t > result[pid]):
                    result[pid] = t
        except Exception:
            pass
        return result

    async def _batch_query_score(self, pids: list[str], codes: list[str], since: datetime) -> dict[str, datetime]:
        """批量查询 score 集合，返回 {patient_id: latest_time}。"""
        result: dict[str, datetime] = {}
        if not codes or not pids:
            return result
        try:
            query = {"$and": [
                {"$or": [{"pid": {"$in": pids}}, {"patient_id": {"$in": pids}}]},
                {"created_at": {"$gte": since}},
                {"$or": [{"score_type": {"$in": codes}}, {"scoreType": {"$in": codes}}]},
            ]}
            cursor = self.db.col("score").find(query, {"pid": 1, "patient_id": 1, "created_at": 1, "time": 1}).sort("created_at", -1).limit(2000)
            async for row in cursor:
                pid = _text(row.get("pid") or row.get("patient_id"))
                t = _dt(row.get("created_at") or row.get("time"))
                if pid and t and (pid not in result or t > result[pid]):
                    result[pid] = t
        except Exception:
            pass
        return result

    async def _batch_query_nurse_reminders(self, pids: list[str], score_types: list[str]) -> dict[str, datetime]:
        """批量查询 nurse_reminders 已解决记录，返回 {patient_id: latest_resolved_at}。"""
        result: dict[str, datetime] = {}
        if not score_types or not pids:
            return result
        try:
            query = {"patient_id": {"$in": pids}, "score_type": {"$in": score_types}, "is_active": False, "resolved_at": {"$ne": None}}
            cursor = self.db.col("nurse_reminders").find(query, {"patient_id": 1, "last_score_time": 1, "resolved_at": 1}).sort("resolved_at", -1).limit(2000)
            async for row in cursor:
                pid = _text(row.get("patient_id"))
                t = _dt(row.get("last_score_time") or row.get("resolved_at"))
                if pid and t and (pid not in result or t > result[pid]):
                    result[pid] = t
        except Exception:
            pass
        return result

    async def _batch_query_alerts(self, pids: list[str], keywords: list[str], since: datetime) -> dict[str, datetime]:
        """批量查询 alert_records，返回 {patient_id: latest_time}。"""
        result: dict[str, datetime] = {}
        regex = "|".join(re.escape(k) for k in keywords if k)
        if not regex or not pids:
            return result
        text_cond = {"$or": [{"rule_id": {"$regex": regex, "$options": "i"}}, {"name": {"$regex": regex, "$options": "i"}}, {"alert_type": {"$regex": regex, "$options": "i"}}]}
        query = {"$and": [{"patient_id": {"$in": pids}}, {"created_at": {"$gte": since}}, text_cond]}
        try:
            cursor = self.db.col("alert_records").find(query, {"patient_id": 1, "created_at": 1}).sort("created_at", -1).limit(2000)
            async for row in cursor:
                pid = _text(row.get("patient_id"))
                t = _dt(row.get("created_at"))
                if pid and t and (pid not in result or t > result[pid]):
                    result[pid] = t
        except Exception:
            pass
        return result

    # ------------------------------------------------------------------
    # 合并多数据源：取最新时间
    # ------------------------------------------------------------------

    @staticmethod
    def _merge_latest(*sources: dict[str, datetime]) -> dict[str, datetime]:
        """合并多个 {pid: time} 字典，每个 pid 取最新 time。"""
        merged: dict[str, datetime] = {}
        for src in sources:
            for pid, t in src.items():
                if pid not in merged or t > merged[pid]:
                    merged[pid] = t
        return merged

    # ------------------------------------------------------------------
    # 主入口：科室每日汇总
    # ------------------------------------------------------------------

    async def daily_summary(self, *, dept: str | None = None, dept_code: str | None = None) -> dict[str, Any]:
        """生成科室每日 bundle 合规汇总，持久化并返回。"""
        now = datetime.now(API_TZ)
        today = now.strftime("%Y-%m-%d")

        # 查已有缓存（1小时内直接返回）
        cached = await self.db.col("bundle_compliance_daily").find_one({"date": today, "dept": dept or "", "deptCode": dept_code or ""})
        if cached:
            gen_at = _dt(cached.get("generated_at"))
            if gen_at and (now - _as_api_tz(gen_at)).total_seconds() < 3600:
                cached.pop("_id", None)
                return cached

        # 获取全科患者
        query: dict[str, Any] = {"status": "admitted"}
        if dept_code:
            query["deptCode"] = dept_code
        elif dept:
            query["$or"] = [{"dept": dept}, {"hisDept": dept}]
        pids: list[str] = []
        try:
            cursor = self.db.col("patient").find(query, {"_id": 1}).limit(160)
            async for row in cursor:
                pid = _text(row.get("_id"))
                if pid:
                    pids.append(pid)
        except Exception:
            pass

        if not pids:
            return self._empty_summary(today, dept, dept_code)

        # 批量查询所有数据源（核心优化：~15次查询替代 ~9600次）
        since_2h = now - timedelta(hours=2)
        since_6h = now - timedelta(hours=6)
        since_12h = now - timedelta(hours=12)
        since_24h = now - timedelta(hours=24)
        since_36h = now - timedelta(hours=36)
        since_48h = now - timedelta(hours=48)
        since_72h = now - timedelta(hours=72)
        since_168h = now - timedelta(hours=168)
        since_192h = now - timedelta(hours=192)

        # 并行批量查询
        results = await self._run_batch_queries(pids, now, {
            "since_6h": since_6h, "since_12h": since_12h, "since_24h": since_24h,
            "since_36h": since_36h, "since_48h": since_48h, "since_72h": since_72h,
            "since_168h": since_168h, "since_192h": since_192h,
        })

        # 计算每个患者每个条目的合规状态
        patient_scores = self._calculate_patient_scores(pids, results)

        # 聚合为科室汇总
        summary = self._aggregate_summary(today, dept, dept_code, pids, patient_scores, now)

        # 持久化
        try:
            await self.db.col("bundle_compliance_daily").update_one(
                {"date": today, "dept": dept or "", "deptCode": dept_code or ""},
                {"$set": summary},
                upsert=True,
            )
        except Exception:
            pass

        return summary

    async def _run_batch_queries(self, pids: list[str], now: datetime, since: dict[str, datetime]) -> dict[str, dict[str, datetime]]:
        """并行执行所有批量查询，返回命名结果字典。"""
        import asyncio

        # ABCDEF: A(CPOT/BPS), C(RASS), D(CAM-ICU) → bedside+score+reminders
        # ABCDEF: B(SAT+SBT) → nurseRecords+alerts
        # ABCDEF: E(early_mobility), F(family) → nurseRecords
        # VAP: hob→bed_angle, oral_care/subglottic/sat→nurseRecords, stress_ulcer→drugExe
        # CLABSI/CAUTI: → nurseRecords

        tasks = {
            # bedside 评分
            "abcdef_a_bedside": self._batch_query_bedside(pids, ["param_score_cpot", "param_score_bps"], since["since_6h"]),
            "abcdef_c_bedside": self._batch_query_bedside(pids, ["param_score_rass_obs"], since["since_6h"]),
            "abcdef_d_bedside": self._batch_query_bedside(pids, ["param_delirium_score"], since["since_12h"]),
            # score 集合
            "abcdef_a_score": self._batch_query_score(pids, ["param_score_cpot", "param_score_bps"], since["since_6h"]),
            "abcdef_c_score": self._batch_query_score(pids, ["param_score_rass_obs"], since["since_6h"]),
            "abcdef_d_score": self._batch_query_score(pids, ["param_delirium_score"], since["since_12h"]),
            # nurse_reminders
            "abcdef_a_reminders": self._batch_query_nurse_reminders(pids, ["cpot", "bps"]),
            "abcdef_c_reminders": self._batch_query_nurse_reminders(pids, ["rass"]),
            "abcdef_d_reminders": self._batch_query_nurse_reminders(pids, ["cam_icu"]),
            # nurseRecords（关键词查询）
            "abcdef_b_sat": self._batch_query_nurse_records(pids, ["sat", "唤醒试验", "停镇静", "镇静中断"], since["since_36h"]),
            "abcdef_b_sbt": self._batch_query_alerts(pids, ["sbt", "自主呼吸", "撤机"], since["since_36h"]),
            "abcdef_e": self._batch_query_nurse_records(pids, ["早期活动", "下床", "站立", "行走", "康复", "活动", "坐起", "床边活动"], since["since_36h"]),
            "abcdef_f": self._batch_query_nurse_records(pids, ["家属沟通", "家属告知", "沟通记录", "家属参与", "探视"], since["since_48h"]),
            # VAP
            "vap_hob_angle": self._batch_query_bed_angle(pids, since["since_6h"]),
            "vap_hob_nr": self._batch_query_nurse_records(pids, ["床头抬高", "抬高床头", "半卧位", "30°", "45°"], since["since_6h"]),
            "vap_oral_care": self._batch_query_nurse_records(pids, ["口腔护理", "口护", "口腔清洁", "oral_care", "oral care"], since["since_6h"]),
            "vap_subglottic": self._batch_query_nurse_records(pids, ["声门下", "吸引", "subglottic"], since["since_12h"]),
            "vap_sat": self._batch_query_nurse_records(pids, ["镇静中断", "自主清醒", "SAT", "停镇静", "暂停镇静"], since["since_36h"]),
            "vap_stress_ulcer": self._batch_query_drug(pids, ["奥美拉唑", "泮托拉唑", "兰索拉唑", "雷贝拉唑", "法莫替丁", "雷尼替丁", "PPI", "H2RA"], since["since_48h"]),
            # CLABSI
            "clabsi_cvc": self._batch_query_nurse_records(pids, ["CVC必要", "中心静脉", "深静脉", "导管必要", "置管评估"], since["since_192h"]),
            "clabsi_dressing": self._batch_query_nurse_records(pids, ["敷料", "换药", "穿刺点", "贴膜"], since["since_36h"]),
            # CAUTI
            "cauti_foley": self._batch_query_nurse_records(pids, ["尿管必要", "导尿管评估", "尿管评估", "foley"], since["since_36h"]),
            "cauti_perineal": self._batch_query_nurse_records(pids, ["尿道口护理", "会阴护理", "尿管护理"], since["since_36h"]),
        }

        # 并行执行所有查询
        keys = list(tasks.keys())
        values = await asyncio.gather(*tasks.values(), return_exceptions=True)
        return {k: (v if isinstance(v, dict) else {}) for k, v in zip(keys, values)}

    def _calculate_patient_scores(self, pids: list[str], r: dict[str, dict[str, datetime]]) -> dict[str, dict[str, Any]]:
        """从批量查询结果计算每个患者每个 bundle 的合规状态。"""
        scores: dict[str, dict[str, Any]] = {}

        # 合并多数据源
        abcdef_a = self._merge_latest(r["abcdef_a_bedside"], r["abcdef_a_score"], r["abcdef_a_reminders"])
        abcdef_c = self._merge_latest(r["abcdef_c_bedside"], r["abcdef_c_score"], r["abcdef_c_reminders"])
        abcdef_d = self._merge_latest(r["abcdef_d_bedside"], r["abcdef_d_score"], r["abcdef_d_reminders"])
        abcdef_b = self._merge_latest(r["abcdef_b_sat"], r["abcdef_b_sbt"])
        vap_hob = self._merge_latest(r["vap_hob_angle"], r["vap_hob_nr"])

        for pid in pids:
            # ABCDEF
            a_hours = _hours_since(abcdef_a.get(pid))
            b_hours = _hours_since(abcdef_b.get(pid))
            c_hours = _hours_since(abcdef_c.get(pid))
            d_hours = _hours_since(abcdef_d.get(pid))
            e_hours = _hours_since(r["abcdef_e"].get(pid))
            f_hours = _hours_since(r["abcdef_f"].get(pid))

            abcdef_items = {
                "A": {"name": "镇痛评估(CPOT/BPS)", "tone": _tone_from_hours(a_hours, 4, 6), "hours": a_hours},
                "B": {"name": "呼吸/SAT/SBT", "tone": _tone_from_hours(b_hours, 24, 36), "hours": b_hours},
                "C": {"name": "意识/镇静(RASS)", "tone": _tone_from_hours(c_hours, 4, 6), "hours": c_hours},
                "D": {"name": "谵妄评估(CAM-ICU)", "tone": _tone_from_hours(d_hours, 8, 12), "hours": d_hours},
                "E": {"name": "早期活动", "tone": _tone_from_hours(e_hours, 24, 36), "hours": e_hours},
                "F": {"name": "家属参与", "tone": _tone_from_hours(f_hours, 24, 48), "hours": f_hours},
            }
            abcdef_green = sum(1 for v in abcdef_items.values() if v["tone"] == "green")
            abcdef_comp = round(abcdef_green / 6.0 * 100, 1)

            # VAP
            hob_hours = _hours_since(vap_hob.get(pid))
            oral_hours = _hours_since(r["vap_oral_care"].get(pid))
            sub_hours = _hours_since(r["vap_subglottic"].get(pid))
            sat_hours = _hours_since(r["vap_sat"].get(pid))
            ulcer_hours = _hours_since(r["vap_stress_ulcer"].get(pid))

            vap_items = {
                "hob": {"name": "床头抬高≥30°", "tone": _tone_from_hours(hob_hours, 4, 6), "hours": hob_hours},
                "oral_care": {"name": "口腔护理q4h", "tone": _tone_from_hours(oral_hours, 4, 6), "hours": oral_hours},
                "subglottic": {"name": "声门下吸引", "tone": _tone_from_hours(sub_hours, 8, 12), "hours": sub_hours},
                "sat": {"name": "镇静中断(SAT)", "tone": _tone_from_hours(sat_hours, 24, 36), "hours": sat_hours},
                "stress_ulcer": {"name": "消化道溃疡预防", "tone": _tone_from_hours(ulcer_hours, 48, 72), "hours": ulcer_hours},
            }
            vap_green = sum(1 for v in vap_items.values() if v["tone"] == "green")
            vap_comp = round(vap_green / len(vap_items) * 100, 1)

            # CLABSI
            cvc_hours = _hours_since(r["clabsi_cvc"].get(pid))
            dress_hours = _hours_since(r["clabsi_dressing"].get(pid))
            clabsi_items = {
                "cvc_review": {"name": "CVC必要性评估", "tone": _tone_from_hours(cvc_hours, 168, 192), "hours": cvc_hours},
                "dressing": {"name": "敷料评估", "tone": _tone_from_hours(dress_hours, 24, 36), "hours": dress_hours},
            }
            clabsi_green = sum(1 for v in clabsi_items.values() if v["tone"] == "green")
            clabsi_comp = round(clabsi_green / len(clabsi_items) * 100, 1)

            # CAUTI
            foley_hours = _hours_since(r["cauti_foley"].get(pid))
            peri_hours = _hours_since(r["cauti_perineal"].get(pid))
            cauti_items = {
                "foley_review": {"name": "尿管必要性", "tone": _tone_from_hours(foley_hours, 24, 36), "hours": foley_hours},
                "perineal": {"name": "尿道口护理", "tone": _tone_from_hours(peri_hours, 24, 36), "hours": peri_hours},
            }
            cauti_green = sum(1 for v in cauti_items.values() if v["tone"] == "green")
            cauti_comp = round(cauti_green / len(cauti_items) * 100, 1)

            scores[pid] = {
                "abcdef": {"items": abcdef_items, "compliance": abcdef_comp, "tone": _tone_from_rate(abcdef_comp)},
                "vap": {"items": vap_items, "compliance": vap_comp, "tone": _tone_from_rate(vap_comp)},
                "clabsi": {"items": clabsi_items, "compliance": clabsi_comp, "tone": _tone_from_rate(clabsi_comp)},
                "cauti": {"items": cauti_items, "compliance": cauti_comp, "tone": _tone_from_rate(cauti_comp)},
            }
        return scores

    def _aggregate_summary(self, date: str, dept: str | None, dept_code: str | None, pids: list[str], patient_scores: dict[str, dict[str, Any]], now: datetime) -> dict[str, Any]:
        """聚合患者评分为科室汇总。"""
        bundle_agg: dict[str, dict[str, Any]] = {}
        for bundle_code in ("abcdef", "vap", "clabsi", "cauti"):
            bundle_def = BUNDLE_DEFINITIONS[bundle_code]
            item_stats: dict[str, dict[str, Any]] = {}
            for item_code, item_def in bundle_def["items"].items():
                item_stats[item_code] = {"name": item_def["name"], "applicable": 0, "compliant": 0, "rate": 0.0}

            compliant_patients = 0
            total_patients = 0
            compliance_sum = 0.0

            for pid in pids:
                bundle_data = patient_scores.get(pid, {}).get(bundle_code, {})
                if not bundle_data:
                    continue
                total_patients += 1
                comp_val = bundle_data.get("compliance", 0)
                compliance_sum += comp_val
                if comp_val >= 100:
                    compliant_patients += 1

                for item_code, item_data in bundle_data.get("items", {}).items():
                    if item_code in item_stats:
                        item_stats[item_code]["applicable"] += 1
                        if item_data.get("tone") == "green":
                            item_stats[item_code]["compliant"] += 1

            for item_code in item_stats:
                applicable = item_stats[item_code]["applicable"]
                if applicable > 0:
                    item_stats[item_code]["rate"] = round(item_stats[item_code]["compliant"] / applicable * 100, 1)

            avg_compliance = round(compliance_sum / total_patients, 1) if total_patients else 0
            bundle_agg[bundle_code] = {
                "code": bundle_code,
                "name": bundle_def["name"],
                "applicable_patients": total_patients,
                "fully_compliant": compliant_patients,
                "avg_compliance": avg_compliance,
                "tone": _tone_from_rate(avg_compliance),
                "items": list(item_stats.values()),
            }

        overall_scores = [v["avg_compliance"] for v in bundle_agg.values() if v["applicable_patients"] > 0]
        overall_score = round(sum(overall_scores) / len(overall_scores), 1) if overall_scores else 0

        return {
            "date": date,
            "dept": dept or "",
            "deptCode": dept_code or "",
            "bundles": bundle_agg,
            "overall_score": overall_score,
            "overall_tone": _tone_from_rate(overall_score),
            "patient_count": len(pids),
            "generated_at": now,
        }

    def _empty_summary(self, date: str, dept: str | None, dept_code: str | None) -> dict[str, Any]:
        return {
            "date": date,
            "dept": dept or "",
            "deptCode": dept_code or "",
            "bundles": {},
            "overall_score": 0,
            "overall_tone": "red",
            "patient_count": 0,
            "generated_at": datetime.now(API_TZ),
        }

    # ------------------------------------------------------------------
    # 单患者评估（供 /patient/{id} 接口使用）
    # ------------------------------------------------------------------

    async def evaluate_patient(self, patient_id: str, patient_doc: dict[str, Any] | None = None) -> dict[str, Any]:
        """评估单个患者所有 bundle。复用批量查询逻辑。"""
        pid = str(patient_id)
        if not pid:
            return {}
        now = datetime.now(API_TZ)
        batch = await self._run_batch_queries([pid], now, {
            "since_6h": now - timedelta(hours=6),
            "since_12h": now - timedelta(hours=12),
            "since_24h": now - timedelta(hours=24),
            "since_36h": now - timedelta(hours=36),
            "since_48h": now - timedelta(hours=48),
            "since_72h": now - timedelta(hours=72),
            "since_168h": now - timedelta(hours=168),
            "since_192h": now - timedelta(hours=192),
        })
        all_scores = self._calculate_patient_scores([pid], batch)
        result = all_scores.get(pid, {})
        result["patient_id"] = pid
        return result
