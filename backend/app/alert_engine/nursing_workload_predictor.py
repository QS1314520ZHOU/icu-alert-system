"""ICU nursing workload prediction and staffing heuristics."""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any

from app.utils.parse import _parse_number

from .scanner_nursing_workload import NursingWorkloadScanner


class NursingWorkloadPredictorMixin:
    def _nursing_workload_cfg(self) -> dict[str, Any]:
        cfg = self.config.yaml_cfg.get("alert_engine", {}).get("nursing_workload", {})
        return cfg if isinstance(cfg, dict) else {}

    def _account_collection_name(self) -> str:
        cfg = self._nursing_workload_cfg()
        return str(cfg.get("account_collection") or "account").strip() or "account"

    def _department_code_tokens(self, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, (list, tuple, set)):
            parts = [str(item).strip() for item in value]
        else:
            parts = [part.strip() for part in str(value).split(",")]
        return [part for part in parts if part]

    def _nursing_workload_level(self, nas_score: float | int | None) -> str:
        score = float(nas_score or 0.0)
        if score >= 85:
            return "extreme"
        if score >= 65:
            return "high"
        if score >= 45:
            return "medium"
        return "low"

    def _nursing_workload_label(self, level: str) -> str:
        return {
            "low": "低",
            "medium": "中",
            "high": "高",
            "extreme": "极高",
        }.get(str(level or "").lower(), "中")

    def _nursing_workload_color(self, level: str) -> str:
        return {
            "low": "#34d399",
            "medium": "#38bdf8",
            "high": "#fb923c",
            "extreme": "#f43f5e",
        }.get(str(level or "").lower(), "#38bdf8")

    def _nursing_burden_rank(self, level: str) -> int:
        return {"low": 1, "medium": 2, "high": 3, "extreme": 4}.get(str(level or "").lower(), 0)

    def _nursing_shift_hours(self) -> float:
        cfg = self._nursing_workload_cfg()
        try:
            return max(4.0, float(cfg.get("shift_hours", 8) or 8))
        except Exception:
            return 8.0

    def _account_text(self, doc: dict[str, Any], keys: list[str]) -> str:
        for key in keys:
            value = doc.get(key)
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text
        return ""

    def _account_flag(self, value: Any) -> bool | None:
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return float(value) != 0
        text = str(value).strip().lower()
        if text in {"1", "true", "yes", "y", "valid", "active", "enabled", "在职", "启用", "有效", "正常"}:
            return True
        if text in {"0", "false", "no", "n", "invalid", "inactive", "disabled", "离职", "停用", "无效", "禁用"}:
            return False
        return None

    def _is_effective_account(self, doc: dict[str, Any]) -> bool:
        valid_text = str(doc.get("valid") or "").strip().lower()
        if valid_text:
            return valid_text == "valid"
        flags = [
            self._account_flag(doc.get("isValid")),
            self._account_flag(doc.get("enabled")),
            self._account_flag(doc.get("isEnabled")),
            self._account_flag(doc.get("active")),
            self._account_flag(doc.get("isActive")),
            self._account_flag(doc.get("status")),
            self._account_flag(doc.get("state")),
        ]
        decided = [flag for flag in flags if flag is not None]
        return all(decided) if decided else True

    def _is_nurse_account(self, doc: dict[str, Any]) -> bool:
        profession = self._account_text(doc, ["profession"]).strip()
        if profession:
            return profession in {"Nurse", "NurseLeader", "Matron", "PracticeNurse"}
        joined = self._account_text(
            doc,
            [
                "jobTitle", "title", "role", "roles",
                "userType", "jobType", "staffType", "职业", "岗位", "职务", "角色", "用户类型",
            ],
        ).lower().strip()
        if not joined:
            return False
        return any(token in joined for token in ["护士", "护理", "nurse", "rn"])

    def _account_dept_name(self, doc: dict[str, Any]) -> str:
        return self._account_text(doc, ["dept", "department", "deptName", "departmentName", "科室", "部门"])

    def _account_dept_code(self, doc: dict[str, Any]) -> str:
        raw = self._account_text(doc, ["departmentCode", "deptCode", "科室编码", "部门编码"])
        return ",".join(self._department_code_tokens(raw))

    async def _effective_nurse_staffing_map(self) -> dict[str, dict[str, Any]]:
        projection = {
            "profession": 1,
            "jobTitle": 1,
            "title": 1,
            "role": 1,
            "roles": 1,
            "userType": 1,
            "jobType": 1,
            "staffType": 1,
            "职业": 1,
            "岗位": 1,
            "职务": 1,
            "角色": 1,
            "用户类型": 1,
            "valid": 1,
            "isValid": 1,
            "enabled": 1,
            "isEnabled": 1,
            "active": 1,
            "isActive": 1,
            "status": 1,
            "state": 1,
            "dept": 1,
            "department": 1,
            "deptName": 1,
            "departmentName": 1,
            "科室": 1,
            "部门": 1,
            "deptCode": 1,
            "departmentCode": 1,
            "科室编码": 1,
            "部门编码": 1,
            "name": 1,
            "username": 1,
            "loginName": 1,
            "userName": 1,
            "account": 1,
            "工号": 1,
        }
        rows = [row async for row in self.db.col(self._account_collection_name()).find({}, projection)]
        staffing: dict[str, dict[str, Any]] = {}
        for row in rows:
            if not self._is_effective_account(row):
                continue
            if not self._is_nurse_account(row):
                continue
            dept_name = self._account_dept_name(row)
            dept_code = self._account_dept_code(row)
            dept_codes = self._department_code_tokens(dept_code) or [""]
            staff_name = self._account_text(row, ["trueName", "name", "username", "loginName", "userName", "account", "工号"])
            for code in dept_codes:
                key = f"{dept_name}|{code}"
                entry = staffing.setdefault(
                    key,
                    {
                        "dept": dept_name or "未知科室",
                        "deptCode": code,
                        "effective_nurse_count": 0,
                        "staff_names": [],
                    },
                )
                entry["effective_nurse_count"] += 1
                if staff_name and len(entry["staff_names"]) < 10:
                    entry["staff_names"].append(staff_name)
        return staffing

    async def _estimate_patient_nursing_workload(
        self,
        patient_doc: dict[str, Any],
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now = now or datetime.now()
        cfg = self._nursing_workload_cfg()
        pid = patient_doc.get("_id")
        pid_str = str(pid or "")
        his_pid = patient_doc.get("hisPid")
        shift_hours = self._nursing_shift_hours()
        alert_window_hours = int(cfg.get("recent_alert_window_hours", 6) or 6)
        nursing_window_hours = int(cfg.get("nursing_context_hours", 24) or 24)

        vitals = await self._get_latest_vitals_by_patient(pid) if pid is not None else {}
        labs = await self._get_latest_labs_map(his_pid, lookback_hours=72) if his_pid else {}
        nursing_context = {}
        if hasattr(self, "_collect_nursing_context"):
            try:
                nursing_context = await self._collect_nursing_context(patient_doc, pid_str, hours=nursing_window_hours)
            except Exception:
                nursing_context = {}

        latest_rass = await self._get_latest_assessment(pid, "rass") if pid is not None else None
        latest_braden = await self._get_latest_assessment(pid, "braden") if pid is not None else None
        latest_delirium = await self._get_latest_assessment(pid, "delirium") if pid is not None else None
        vaso_level = await self._get_vasopressor_level(pid) if pid is not None else 0

        active_device_binds = []
        if pid_str:
            active_device_binds = [
                row async for row in self.db.col("deviceBind").find(
                    {"pid": pid_str, "unBindTime": None},
                    {"type": 1, "deviceName": 1, "name": 1, "bindTime": 1},
                )
            ]

        device_types: set[str] = set()
        for row in active_device_binds:
            dtype = str(row.get("type") or "").strip().lower()
            name = str(row.get("deviceName") or row.get("name") or "").lower()
            if dtype:
                device_types.add(dtype)
            elif "呼吸机" in name or "vent" in name:
                device_types.add("vent")
            elif "crrt" in name or "血滤" in name or "血液净化" in name:
                device_types.add("crrt")
            elif "监护" in name or "monitor" in name:
                device_types.add("monitor")

        has_vent = "vent" in device_types
        has_crrt = "crrt" in device_types
        device_burden = min(len(active_device_binds), 4)

        recent_alerts = []
        if pid_str:
            recent_alerts = [
                row async for row in self.db.col("alert_records").find(
                    {"patient_id": {"$in": [pid_str, pid]}, "created_at": {"$gte": now - timedelta(hours=alert_window_hours)}},
                    {"severity": 1, "alert_type": 1, "name": 1, "created_at": 1},
                ).sort("created_at", -1).limit(30)
            ]
        critical_alerts = sum(1 for row in recent_alerts if str(row.get("severity") or "").lower() == "critical")
        high_alerts = sum(1 for row in recent_alerts if str(row.get("severity") or "").lower() == "high")

        plans = nursing_context.get("plans") if isinstance(nursing_context.get("plans"), dict) else {}
        pending_plans = int(plans.get("pending_count") or 0)
        delayed_plans = int(plans.get("delayed_count") or 0)
        note_records = nursing_context.get("records") if isinstance(nursing_context.get("records"), list) else []
        note_signal_count = len([row for row in note_records[:8] if str((row or {}).get("text") or "").strip()])

        lactate = None
        creatinine = None
        bilirubin = None
        platelets = None
        if isinstance(labs.get("lac"), dict):
            lactate = _parse_number(labs.get("lac", {}).get("value"))
        elif isinstance(labs.get("lactate"), dict):
            lactate = _parse_number(labs.get("lactate", {}).get("value"))
        if isinstance(labs.get("cr"), dict):
            creatinine = _parse_number(labs.get("cr", {}).get("value"))
        if isinstance(labs.get("tbil"), dict):
            bilirubin = _parse_number(labs.get("tbil", {}).get("value"))
        if isinstance(labs.get("plt"), dict):
            platelets = _parse_number(labs.get("plt", {}).get("value"))

        hr = _parse_number(vitals.get("hr")) if isinstance(vitals, dict) else None
        rr = _parse_number(vitals.get("rr")) if isinstance(vitals, dict) else None
        sbp = _parse_number(vitals.get("sbp")) if isinstance(vitals, dict) else None
        map_value = _parse_number(vitals.get("map")) if isinstance(vitals, dict) else None

        fio2_fraction = None
        peep = None
        if has_vent:
            device_id = await self._get_device_id_for_patient(patient_doc, ["vent"])
            if device_id:
                vent_cap = await self._get_latest_device_cap(
                    device_id,
                    codes=["param_FiO2", "param_vent_measure_peep", "param_vent_peep", "param_vent_resp"],
                )
                if vent_cap:
                    fio2 = self._vent_param(vent_cap, "fio2", "param_FiO2")
                    if fio2 is not None:
                        fio2_fraction = round((fio2 / 100.0) if fio2 > 1 else fio2, 3)
                    peep = self._vent_param_priority(
                        vent_cap,
                        ["peep_measured", "peep_set"],
                        ["param_vent_measure_peep", "param_vent_peep"],
                    )

        workload_points = float(cfg.get("base_points", 18) or 18)
        drivers: list[str] = []

        def add_points(points: float, text: str) -> None:
            nonlocal workload_points
            workload_points += points
            if text and text not in drivers:
                drivers.append(text)

        if has_vent:
            add_points(float(cfg.get("ventilation_points", 12) or 12), "机械通气支持")
            if fio2_fraction is not None and fio2_fraction >= 0.6:
                add_points(4, f"FiO2 {round(fio2_fraction, 2)}")
            if peep is not None and peep >= 10:
                add_points(3, f"PEEP {round(float(peep), 1)} cmH2O")

        if has_crrt:
            add_points(float(cfg.get("crrt_points", 8) or 8), "CRRT/血液净化支持")

        if vaso_level >= 3:
            add_points(float(cfg.get("vasopressor_points_high", 10) or 10), "血管活性药高负荷支持")
        elif vaso_level > 0:
            add_points(float(cfg.get("vasopressor_points", 6) or 6), "血管活性药支持")

        if map_value is not None and map_value < 65:
            add_points(4, f"MAP {round(map_value, 1)} mmHg")
        if sbp is not None and sbp < 90:
            add_points(3, f"SBP {round(sbp, 1)} mmHg")
        if hr is not None and hr >= 130:
            add_points(2, f"HR {round(hr, 1)} 次/分")
        if rr is not None and rr >= 30:
            add_points(3, f"RR {round(rr, 1)} 次/分")

        if lactate is not None and lactate >= 4:
            add_points(6, f"乳酸 {round(lactate, 2)} mmol/L")
        elif lactate is not None and lactate >= 2:
            add_points(4, f"乳酸升高 {round(lactate, 2)} mmol/L")

        if creatinine is not None and creatinine >= 177:
            add_points(3, f"肌酐 {round(creatinine, 1)}")
        if bilirubin is not None and bilirubin >= 34:
            add_points(2, f"胆红素 {round(bilirubin, 1)}")
        if platelets is not None and platelets < 100:
            add_points(2, f"血小板 {round(platelets, 1)}")

        if latest_rass is not None and (latest_rass <= -3 or latest_rass >= 2):
            add_points(3, f"RASS {round(float(latest_rass), 1)}")
        if latest_braden is not None and latest_braden <= 12:
            add_points(3, f"Braden {round(float(latest_braden), 1)}")
        if latest_delirium is not None and latest_delirium > 0:
            add_points(2, "谵妄/意识波动风险")

        if critical_alerts:
            add_points(min(critical_alerts * 3, 9), f"{critical_alerts} 条危急预警")
        if high_alerts:
            add_points(min(high_alerts * 1.5, 6), f"{high_alerts} 条高危预警")

        if device_burden:
            add_points(min(device_burden * 1.5, 5), f"{device_burden} 类设备并行管理")
        if pending_plans:
            add_points(min(pending_plans * 1.2, 4), f"{pending_plans} 项护理计划待执行")
        if delayed_plans:
            add_points(min(delayed_plans * 1.5, 4), f"{delayed_plans} 项护理计划延迟")
        if note_signal_count:
            add_points(min(note_signal_count, 3), f"{note_signal_count} 条护理观察信号")

        nas_scale = float(cfg.get("nas_scale", 1.65) or 1.65)
        nas_offset = float(cfg.get("nas_offset", 16) or 16)
        nas_score = round(min(100.0, max(20.0, nas_offset + workload_points * nas_scale)), 1)
        tiss28_score = round(min(56.0, max(8.0, 6 + workload_points * 0.82)), 1)
        level = self._nursing_workload_level(nas_score)
        next_shift_hours = round(nas_score * shift_hours / 100.0, 2)
        recommended_nurse_ratio = round(next_shift_hours / shift_hours, 2)

        return {
            "patient_id": pid_str,
            "patient_name": patient_doc.get("name") or patient_doc.get("hisName") or "",
            "bed": patient_doc.get("hisBed") or patient_doc.get("bed") or "",
            "dept": patient_doc.get("dept") or patient_doc.get("hisDept") or "未知科室",
            "deptCode": patient_doc.get("deptCode") or "",
            "score_type": "nursing_workload_prediction",
            "prediction_horizon_hours": shift_hours,
            "nas_score": nas_score,
            "tiss28_score": tiss28_score,
            "workload_points": round(workload_points, 2),
            "intensity_level": level,
            "intensity_label": self._nursing_workload_label(level),
            "intensity_color": self._nursing_workload_color(level),
            "predicted_next_shift_hours": next_shift_hours,
            "recommended_nurse_ratio": recommended_nurse_ratio,
            "active_alerts_6h": len(recent_alerts),
            "critical_alerts_6h": critical_alerts,
            "high_alerts_6h": high_alerts,
            "active_device_types": sorted(device_types),
            "device_burden": device_burden,
            "hemodynamics": {
                "map": map_value,
                "sbp": sbp,
                "hr": hr,
                "rr": rr,
                "vasopressor_level": vaso_level,
            },
            "respiratory_support": {
                "ventilated": has_vent,
                "fio2_fraction": fio2_fraction,
                "peep": peep,
            },
            "nursing_context_summary": {
                "pending_count": pending_plans,
                "delayed_count": delayed_plans,
                "record_count": len(note_records),
            },
            "drivers": drivers[:8],
            "generated_at": now,
            "calc_time": now,
            "updated_at": now,
            "month": now.strftime("%Y-%m"),
            "day": now.strftime("%Y-%m-%d"),
        }

    async def _persist_nursing_workload_prediction(
        self,
        patient_doc: dict[str, Any],
        prediction: dict[str, Any],
        *,
        now: datetime,
    ) -> dict[str, Any]:
        pid_str = str(prediction.get("patient_id") or "")
        payload = {
            **prediction,
            "patient_name": patient_doc.get("name") or patient_doc.get("hisName") or "",
            "bed": patient_doc.get("hisBed") or patient_doc.get("bed") or "",
            "dept": patient_doc.get("dept") or patient_doc.get("hisDept") or "未知科室",
            "deptCode": patient_doc.get("deptCode") or "",
            "score": prediction.get("nas_score"),
            "calc_time": now,
            "updated_at": now,
            "month": now.strftime("%Y-%m"),
            "day": now.strftime("%Y-%m-%d"),
        }
        latest = await self.db.col("score_records").find_one(
            {
                "patient_id": pid_str,
                "score_type": "nursing_workload_prediction",
                "calc_time": {"$gte": now - timedelta(minutes=90)},
            },
            sort=[("calc_time", -1)],
        )
        if latest:
            await self.db.col("score_records").update_one({"_id": latest["_id"]}, {"$set": payload})
            payload["_id"] = latest["_id"]
        else:
            res = await self.db.col("score_records").insert_one(payload)
            payload["_id"] = res.inserted_id
        return payload

    def _build_department_workload_summary(
        self,
        *,
        dept: str,
        dept_code: str,
        rows: list[dict[str, Any]],
        staffing: dict[str, Any] | None = None,
        now: datetime,
    ) -> dict[str, Any]:
        shift_hours = self._nursing_shift_hours()
        sorted_rows = sorted(
            rows,
            key=lambda item: (
                self._nursing_burden_rank(str(item.get("intensity_level") or "")),
                float(item.get("nas_score") or 0.0),
            ),
            reverse=True,
        )
        patient_count = len(sorted_rows)
        total_shift_hours = round(sum(float(item.get("predicted_next_shift_hours") or 0.0) for item in sorted_rows), 2)
        recommended_nurse_count = round(total_shift_hours / shift_hours, 2) if shift_hours > 0 else 0.0
        workload_distribution = {
            "low": sum(1 for item in sorted_rows if str(item.get("intensity_level")) == "low"),
            "medium": sum(1 for item in sorted_rows if str(item.get("intensity_level")) == "medium"),
            "high": sum(1 for item in sorted_rows if str(item.get("intensity_level")) == "high"),
            "extreme": sum(1 for item in sorted_rows if str(item.get("intensity_level")) == "extreme"),
        }
        total_nas = round(sum(float(item.get("nas_score") or 0.0) for item in sorted_rows), 1)
        avg_nas = round(total_nas / patient_count, 1) if patient_count else 0.0
        effective_nurse_count = int((staffing or {}).get("effective_nurse_count") or 0)
        staffing_gap = round(recommended_nurse_count - effective_nurse_count, 2)
        return {
            "score_type": "nursing_workload_department_summary",
            "dept": dept or "未知科室",
            "deptCode": dept_code or "",
            "patient_count": patient_count,
            "total_nas_score": total_nas,
            "avg_nas_score": avg_nas,
            "total_predicted_shift_hours": total_shift_hours,
            "recommended_nurse_count": recommended_nurse_count,
            "recommended_nurse_ceiling": int(math.ceil(recommended_nurse_count or 0.0)),
            "effective_nurse_count": effective_nurse_count,
            "staffing_gap": staffing_gap,
            "staffing_gap_ceiling": int(math.ceil(max(staffing_gap, 0.0))),
            "high_patient_count": workload_distribution["high"],
            "extreme_patient_count": workload_distribution["extreme"],
            "workload_distribution": workload_distribution,
            "staff_names": list((staffing or {}).get("staff_names") or [])[:10],
            "top_patients": [
                {
                    "patient_id": item.get("patient_id"),
                    "patient_name": item.get("patient_name"),
                    "bed": item.get("bed"),
                    "intensity_level": item.get("intensity_level"),
                    "intensity_label": item.get("intensity_label"),
                    "nas_score": item.get("nas_score"),
                    "predicted_next_shift_hours": item.get("predicted_next_shift_hours"),
                }
                for item in sorted_rows[:5]
            ],
            "calc_time": now,
            "updated_at": now,
            "month": now.strftime("%Y-%m"),
            "day": now.strftime("%Y-%m-%d"),
        }

    async def _persist_department_workload_summary(self, summary: dict[str, Any], *, now: datetime) -> None:
        dept = str(summary.get("dept") or "")
        latest = await self.db.col("score_records").find_one(
            {
                "score_type": "nursing_workload_department_summary",
                "dept": dept,
                "calc_time": {"$gte": now - timedelta(minutes=90)},
            },
            sort=[("calc_time", -1)],
        )
        if latest:
            await self.db.col("score_records").update_one({"_id": latest["_id"]}, {"$set": summary})
        else:
            await self.db.col("score_records").insert_one(summary)

    async def scan_nursing_workload(self) -> list[dict[str, Any]]:
        now = datetime.now()
        patient_cursor = self.db.col("patient").find(
            self._active_patient_query(),
            {
                "name": 1,
                "hisName": 1,
                "hisBed": 1,
                "bed": 1,
                "dept": 1,
                "hisDept": 1,
                "deptCode": 1,
                "hisPid": 1,
                "nursingLevel": 1,
                "icuAdmissionTime": 1,
                "weight": 1,
                "bodyWeight": 1,
                "body_weight": 1,
                "weightKg": 1,
                "weight_kg": 1,
            },
        )
        patients = [row async for row in patient_cursor]
        if not patients:
            return []

        persisted: list[dict[str, Any]] = []
        by_dept: dict[tuple[str, str], list[dict[str, Any]]] = {}
        staffing_map: dict[str, dict[str, Any]] = {}
        try:
            staffing_map = await self._effective_nurse_staffing_map()
        except Exception:
            staffing_map = {}
        for patient_doc in patients:
            try:
                prediction = await self._estimate_patient_nursing_workload(patient_doc, now=now)
                record = await self._persist_nursing_workload_prediction(patient_doc, prediction, now=now)
                persisted.append(record)
                dept_key = (
                    str(record.get("dept") or patient_doc.get("dept") or patient_doc.get("hisDept") or "未知科室"),
                    str(record.get("deptCode") or patient_doc.get("deptCode") or ""),
                )
                by_dept.setdefault(dept_key, []).append(record)
            except Exception:
                continue

        for (dept, dept_code), rows in by_dept.items():
            summary = self._build_department_workload_summary(
                dept=dept,
                dept_code=dept_code,
                rows=rows,
                staffing=(
                    staffing_map.get(f"{dept}|{dept_code}")
                    or staffing_map.get(f"|{dept_code}")
                    or staffing_map.get(f"{dept}|")
                ),
                now=now,
            )
            await self._persist_department_workload_summary(summary, now=now)

        return persisted

    async def latest_nursing_workload_predictions(
        self,
        *,
        dept: str | None = None,
        dept_code: str | None = None,
        hours: int = 12,
    ) -> list[dict[str, Any]]:
        since = datetime.now() - timedelta(hours=max(1, int(hours or 12)))
        query: dict[str, Any] = {"score_type": "nursing_workload_prediction", "calc_time": {"$gte": since}}
        if dept:
            query["dept"] = dept
        if dept_code:
            query["deptCode"] = dept_code
        cursor = self.db.col("score_records").find(query).sort("calc_time", -1)
        latest: dict[str, dict[str, Any]] = {}
        async for row in cursor:
            pid = str(row.get("patient_id") or "").strip()
            if not pid or pid in latest:
                continue
            latest[pid] = row
        return list(latest.values())

    async def latest_nursing_department_summaries(
        self,
        *,
        dept: str | None = None,
        dept_code: str | None = None,
        hours: int = 12,
    ) -> list[dict[str, Any]]:
        since = datetime.now() - timedelta(hours=max(1, int(hours or 12)))
        query: dict[str, Any] = {"score_type": "nursing_workload_department_summary", "calc_time": {"$gte": since}}
        if dept:
            query["dept"] = dept
        if dept_code:
            query["deptCode"] = dept_code
        cursor = self.db.col("score_records").find(query).sort("calc_time", -1)
        latest: dict[str, dict[str, Any]] = {}
        async for row in cursor:
            key = f"{row.get('dept') or ''}|{row.get('deptCode') or ''}"
            if key in latest:
                continue
            latest[key] = row
        return list(latest.values())

    async def get_nursing_workload_analytics(
        self,
        *,
        dept: str | None = None,
        dept_code: str | None = None,
        hours: int = 12,
    ) -> dict[str, Any]:
        patient_rows = await self.latest_nursing_workload_predictions(dept=dept, dept_code=dept_code, hours=hours)
        if not patient_rows:
            fresh_rows = await self.scan_nursing_workload()
            patient_rows = [
                row for row in fresh_rows
                if (not dept or str(row.get("dept") or "") == dept)
                and (not dept_code or str(row.get("deptCode") or "") == dept_code)
            ]

        dept_rows = await self.latest_nursing_department_summaries(dept=dept, dept_code=dept_code, hours=hours)
        if not dept_rows and patient_rows:
            grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
            now = datetime.now()
            try:
                staffing_map = await self._effective_nurse_staffing_map()
            except Exception:
                staffing_map = {}
            for row in patient_rows:
                grouped.setdefault((str(row.get("dept") or "未知科室"), str(row.get("deptCode") or "")), []).append(row)
            dept_rows = [
                self._build_department_workload_summary(
                    dept=k[0],
                    dept_code=k[1],
                    rows=v,
                    staffing=(
                        staffing_map.get(f"{k[0]}|{k[1]}")
                        or staffing_map.get(f"|{k[1]}")
                        or staffing_map.get(f"{k[0]}|")
                    ),
                    now=now,
                )
                for k, v in grouped.items()
            ]

        patient_rows = sorted(
            patient_rows,
            key=lambda item: (
                self._nursing_burden_rank(str(item.get("intensity_level") or "")),
                float(item.get("nas_score") or 0.0),
            ),
            reverse=True,
        )
        dept_rows = sorted(
            dept_rows,
            key=lambda item: (
                float(item.get("recommended_nurse_count") or 0.0),
                int(item.get("extreme_patient_count") or 0),
                int(item.get("high_patient_count") or 0),
            ),
            reverse=True,
        )

        x_labels = [f"{row.get('dept') or '未知'}-{row.get('bed') or '--'}" for row in patient_rows[:30]]
        y_labels = ["未来一个班次"]
        heatmap_data = [
            [idx, 0, round(float(row.get("nas_score") or 0.0), 1)]
            for idx, row in enumerate(patient_rows[:30])
        ]

        total_patients = len(patient_rows)
        total_shift_hours = round(sum(float(row.get("predicted_next_shift_hours") or 0.0) for row in patient_rows), 2)
        shift_hours = self._nursing_shift_hours()
        total_recommended = round(total_shift_hours / shift_hours, 2) if shift_hours > 0 else 0.0
        total_effective_nurses = sum(int(row.get("effective_nurse_count") or 0) for row in dept_rows)
        total_staffing_gap = round(total_recommended - total_effective_nurses, 2)
        high_and_extreme = sum(
            1 for row in patient_rows if str(row.get("intensity_level") or "") in {"high", "extreme"}
        )
        timeline_cursor = self.db.col("score_records").find(
            {
                "score_type": "nursing_workload_department_summary",
                "calc_time": {"$gte": datetime.now() - timedelta(hours=max(hours, 1))},
                **({"dept": dept} if dept else {}),
                **({"deptCode": dept_code} if dept_code else {}),
            },
            {
                "dept": 1,
                "calc_time": 1,
                "total_predicted_shift_hours": 1,
                "recommended_nurse_count": 1,
                "high_patient_count": 1,
                "extreme_patient_count": 1,
            },
        ).sort("calc_time", 1)
        timeline = [row async for row in timeline_cursor]
        return {
            "summary": {
                "patient_count": total_patients,
                "total_predicted_shift_hours": total_shift_hours,
                "recommended_nurse_count": total_recommended,
                "recommended_nurse_ceiling": int(math.ceil(total_recommended or 0.0)),
                "effective_nurse_count": total_effective_nurses,
                "staffing_gap": total_staffing_gap,
                "staffing_gap_ceiling": int(math.ceil(max(total_staffing_gap, 0.0))),
                "high_and_extreme_count": high_and_extreme,
                "extreme_count": sum(1 for row in patient_rows if str(row.get("intensity_level") or "") == "extreme"),
                "peak_dept": dept_rows[0].get("dept") if dept_rows else None,
                "peak_dept_nurse_count": dept_rows[0].get("recommended_nurse_count") if dept_rows else None,
                "window_hours": max(1, int(hours or 12)),
                "shift_hours": shift_hours,
            },
            "dept_rows": dept_rows,
            "patient_rows": patient_rows[:30],
            "heatmap": {
                "x_labels": x_labels,
                "y_labels": y_labels,
                "data": heatmap_data,
            },
            "timeline": timeline,
        }

    async def run_nursing_workload_scan(self) -> None:
        await NursingWorkloadScanner(self).scan()
