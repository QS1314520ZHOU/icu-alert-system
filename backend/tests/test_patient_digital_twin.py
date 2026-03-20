import unittest
from datetime import datetime, timedelta

from bson import ObjectId

from app.services.patient_digital_twin import PatientDigitalTwinService


class _Cursor:
    def __init__(self, docs):
        self._docs = list(docs)
        self._idx = 0

    def sort(self, key, direction=None):
        if isinstance(key, list):
            sort_key, sort_direction = key[0]
        else:
            sort_key, sort_direction = key, direction
        reverse = sort_direction == -1
        self._docs.sort(key=lambda item: item.get(sort_key) or datetime.min, reverse=reverse)
        return self

    def limit(self, count):
        self._docs = self._docs[:count]
        return self

    def __aiter__(self):
        self._idx = 0
        return self

    async def __anext__(self):
        if self._idx >= len(self._docs):
            raise StopAsyncIteration
        item = self._docs[self._idx]
        self._idx += 1
        return item


class _Collection:
    def __init__(self, docs=None):
        self.docs = [dict(doc) for doc in (docs or [])]

    def find(self, query=None, projection=None):
        query = query or {}
        matched = [doc for doc in self.docs if self._match(doc, query)]
        if projection:
            reduced = []
            for doc in matched:
                row = {}
                for key, enabled in projection.items():
                    if enabled and key in doc:
                        row[key] = doc[key]
                if "_id" in doc:
                    row["_id"] = doc["_id"]
                reduced.append(row)
            matched = reduced
        return _Cursor(matched)

    async def find_one(self, query, sort=None):
        docs = [doc for doc in self.docs if self._match(doc, query)]
        if sort:
            sort_key, sort_direction = sort[0]
            docs.sort(key=lambda item: item.get(sort_key) or datetime.min, reverse=sort_direction == -1)
        return dict(docs[0]) if docs else None

    async def update_one(self, selector, update):
        for doc in self.docs:
            if self._match(doc, selector):
                for key, value in update.get("$set", {}).items():
                    doc[key] = value
                return

    async def insert_one(self, doc):
        item = dict(doc)
        item.setdefault("_id", ObjectId())
        self.docs.append(item)

        class _Result:
            inserted_id = item["_id"]

        return _Result()

    @staticmethod
    def _match(doc, query):
        for key, value in query.items():
            if isinstance(value, dict):
                current = doc.get(key)
                if "$gte" in value and not (current >= value["$gte"]):
                    return False
                if "$in" in value and current not in value["$in"]:
                    return False
            elif doc.get(key) != value:
                return False
        return True


class _FakeDb:
    def __init__(self, collections=None):
        self.collections = collections or {}

    def col(self, name):
        if name not in self.collections:
            self.collections[name] = _Collection()
        return self.collections[name]


class _FakeConfig:
    yaml_cfg = {"ai_service": {"patient_digital_twin": {"tracked_labs": ["lac", "cr"]}}}


class _FakeAlertEngine:
    def _cfg(self, *path, default=None):
        if path == ("vital_signs", "temperature", "code"):
            return "param_T"
        return default

    async def _collect_patient_facts(self, patient_doc, pid):
        return {"active_alerts": [{"alert_type": "shock"}], "urine_ml_kg_h_6h": 0.64}

    async def _get_latest_vitals_by_patient(self, patient_id):
        return {"hr": 108, "map": 61, "spo2": 93}

    async def _get_param_series_by_pid(self, patient_id, code, since, prefer_device_types=None, limit=480):
        base = datetime.now() - timedelta(hours=1)
        samples = {
            "param_HR": [{"time": base, "value": 102}, {"time": base + timedelta(minutes=30), "value": 108}],
            "param_ibp_m": [{"time": base, "value": 64}, {"time": base + timedelta(minutes=30), "value": 61}],
            "param_spo2": [{"time": base, "value": 95}, {"time": base + timedelta(minutes=30), "value": 93}],
            "param_resp": [{"time": base, "value": 20}, {"time": base + timedelta(minutes=30), "value": 24}],
            "param_T": [{"time": base, "value": 37.2}, {"time": base + timedelta(minutes=30), "value": 38.0}],
        }
        return list(samples.get(code, []))

    async def _get_latest_labs_map(self, his_pid, lookback_hours=24):
        return {"lac": {"value": 3.2, "time": datetime.now() - timedelta(minutes=20)}, "cr": {"value": 156, "time": datetime.now() - timedelta(minutes=40)}}

    async def _get_lab_series(self, his_pid, key, since, limit=80):
        base = datetime.now() - timedelta(hours=2)
        rows = {
            "lac": [{"time": base, "value": 2.4}, {"time": base + timedelta(hours=1), "value": 3.2}],
            "cr": [{"time": base, "value": 132}, {"time": base + timedelta(hours=1), "value": 156}],
        }
        return list(rows.get(key, []))

    async def _get_recent_drug_docs_window(self, patient_id, hours=24, limit=300):
        return [{"drugName": "去甲肾上腺素", "executeTime": datetime.now() - timedelta(minutes=35), "_event_time": datetime.now() - timedelta(minutes=35), "dose": "0.12 ug/kg/min", "doseUnit": "ug/kg/min", "route": "iv", "status": "running"}]

    def _get_patient_weight(self, patient_doc):
        return 70.0

    def _extract_vasopressor_rate_ug_kg_min(self, doc, weight_kg):
        return 0.12

    async def _calc_sofa(self, patient_doc, pid, device_id, his_pid):
        return {"score": 9}

    async def _get_device_id_for_patient(self, patient_doc, device_types):
        return "dev-1"

    async def get_imaging_report_analysis(self, patient_doc, patient_id, hours=24, max_age_hours=8, persist_if_refresh=False):
        return {"summary": "胸片提示肺水肿进展", "latest_report_time": datetime.now() - timedelta(minutes=50), "score_type": "imaging_report_signal_analysis"}

    async def latest_nursing_note_analysis(self, patient_id, hours=24):
        return {"summary": "护理记录提示痰量增多", "calc_time": datetime.now() - timedelta(minutes=25), "score_type": "nursing_note_signal_analysis"}


class PatientDigitalTwinServiceTest(unittest.IsolatedAsyncioTestCase):
    async def test_build_snapshot_assembles_multimodal_state_and_timeline(self):
        alert_records = _Collection([
            {"_id": ObjectId(), "patient_id": "p1", "name": "低灌注预警", "alert_type": "shock", "severity": "high", "created_at": datetime.now() - timedelta(minutes=10)}
        ])
        score_records = _Collection([
            {"_id": ObjectId(), "patient_id": "p1", "score_type": "sofa", "score": 9, "summary": "SOFA 9分", "calc_time": datetime.now() - timedelta(minutes=15)}
        ])
        service = PatientDigitalTwinService(db=_FakeDb({"alert_records": alert_records, "score_records": score_records}), alert_engine=_FakeAlertEngine(), config=_FakeConfig())

        patient = {"_id": "p1", "name": "张三", "hisPid": "H1", "hisBed": "12", "dept": "ICU", "clinicalDiagnosis": "脓毒症"}
        snapshot = await service.build_snapshot("p1", patient, hours=24)

        self.assertEqual(snapshot["score_type"], "digital_twin_snapshot")
        self.assertEqual(snapshot["snapshot"]["map"]["current"], 61.0)
        self.assertEqual(snapshot["snapshot"]["lactate"]["current"], 3.2)
        self.assertEqual(snapshot["medications"]["vasoactive_support"]["current_dose_ug_kg_min"], 0.12)
        self.assertTrue(snapshot["scores"]["sofa"])
        self.assertGreaterEqual(len(snapshot["timeline"]), 5)
        self.assertEqual(snapshot["timeline"][0]["source"], "alert")

    async def test_persist_snapshot_upserts_recent_record(self):
        existing_id = ObjectId()
        now = datetime.now()
        score_records = _Collection([
            {"_id": existing_id, "patient_id": "p1", "score_type": "digital_twin_snapshot", "calc_time": now - timedelta(minutes=5), "summary": {"timeline_events": 1}}
        ])
        service = PatientDigitalTwinService(db=_FakeDb({"score_records": score_records}), alert_engine=_FakeAlertEngine(), config=_FakeConfig())

        stored = await service.persist_snapshot({"patient_id": "p1", "score_type": "digital_twin_snapshot", "calc_time": now, "summary": {"timeline_events": 9}}, upsert_window_minutes=30)

        self.assertEqual(stored["_id"], existing_id)
        self.assertEqual(len(score_records.docs), 1)
        self.assertEqual(score_records.docs[0]["summary"]["timeline_events"], 9)


if __name__ == "__main__":
    unittest.main()
