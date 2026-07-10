import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace

from bson import ObjectId

from app.services.pulse_service import PulseCandidate, PulseService, ViewerContext


class _Collection:
    def __init__(self, docs=None):
        self.docs = [dict(doc) for doc in (docs or [])]

    async def count_documents(self, query):
        return sum(1 for doc in self.docs if self._match(doc, query))

    async def find_one(self, query, sort=None):
        docs = [doc for doc in self.docs if self._match(doc, query)]
        if sort:
            key, direction = sort[0]
            docs.sort(key=lambda item: item.get(key) or datetime.min, reverse=direction == -1)
        return dict(docs[0]) if docs else None

    @classmethod
    def _match(cls, doc, query):
        for key, value in query.items():
            current = doc.get(key)
            if isinstance(value, dict):
                if "$gte" in value and not (current >= value["$gte"]):
                    return False
                if "$in" in value and current not in value["$in"]:
                    return False
            elif current != value:
                return False
        return True


class _FakeDb:
    def __init__(self, collections):
        self.collections = collections

    def col(self, name):
        return self.collections.setdefault(name, _Collection())


class PulseScoringTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.patient_id = str(ObjectId())
        self.other_patient_id = str(ObjectId())
        self.db = _FakeDb(
            {
                "patient": _Collection(
                    [
                        {"_id": ObjectId(self.patient_id), "deptCode": "ICU-A"},
                        {"_id": ObjectId(self.other_patient_id), "deptCode": "ICU-B"},
                    ]
                ),
                "pulse_events": _Collection(),
            }
        )
        cfg = SimpleNamespace(yaml_cfg={"ai_service": {"pulse": {"push_threshold": 0.55}}})
        self.service = PulseService(db=self.db, config=cfg, ws_mgr=None, alert_engine=None)

    def _candidate(self, *, severity="high", patient_id=None, alert_type="shock", age_minutes=10, owner_role="doctor"):
        patient_id = patient_id or self.patient_id
        return PulseCandidate(
            source="alert",
            event_id=f"{alert_type}_{severity}_{age_minutes}",
            patient_id=patient_id,
            patient_label="3床·张XX",
            severity=severity,
            raw={"alert_type": alert_type, "rule_id": alert_type},
            occurred_at=datetime.now() - timedelta(minutes=age_minutes),
            owner_role=owner_role,
        )

    def _viewer(self, *, role="doctor", dept_code="ICU-A", current_patient_id=None):
        return ViewerContext(
            user_id="doctor_001",
            role=role,
            dept_code=dept_code,
            current_patient_id=current_patient_id,
            current_route="/patient/x",
        )

    async def test_critical_role_and_patient_focus_scores_highest(self):
        viewer = self._viewer(current_patient_id=self.patient_id)
        critical_focused = self._candidate(severity="critical")
        high_focused = self._candidate(severity="high")
        high_other_patient = self._candidate(severity="high", patient_id=self.other_patient_id)

        critical_score = await self.service.score_candidate(critical_focused, viewer)
        high_score = await self.service.score_candidate(high_focused, viewer)
        other_score = await self.service.score_candidate(high_other_patient, viewer)

        self.assertGreater(critical_score, high_score)
        self.assertGreater(high_score, other_score)
        self.assertGreaterEqual(critical_score, 0.95)
        self.assertGreaterEqual(high_score, 0.55)

    async def test_dept_mismatch_is_filtered_out(self):
        viewer = self._viewer(role="nurse", dept_code="ICU-Z", current_patient_id=None)
        candidate = self._candidate(severity="high", owner_role="doctor")

        score = await self.service.score_candidate(candidate, viewer)

        self.assertEqual(score, 0.0)

    async def test_same_dept_still_scores_candidate(self):
        viewer = self._viewer(dept_code="ICU-A")
        candidate = self._candidate(severity="high")

        score = await self.service.score_candidate(candidate, viewer)

        self.assertGreaterEqual(score, 0.55)

    def test_candidate_dept_code_prefers_patient_then_raw(self):
        candidate = self._candidate()
        candidate.raw["deptCode"] = "ICU-RAW"

        patient_dept = self.service._candidate_dept_code(candidate, {"deptCode": "ICU-PATIENT"})
        raw_dept = self.service._candidate_dept_code(candidate)

        self.assertEqual(patient_dept, "ICU-PATIENT")
        self.assertEqual(raw_dept, "ICU-RAW")

    async def test_recent_same_patient_type_is_downweighted_for_novelty(self):
        self.db.col("pulse_events").docs.append(
            {
                "viewer_id": "doctor_001",
                "patient_id": self.patient_id,
                "candidate_type": "alert:shock",
                "pushed_at": datetime.now() - timedelta(minutes=20),
            }
        )
        viewer = self._viewer(current_patient_id=self.patient_id)
        candidate = self._candidate(severity="critical", alert_type="shock")

        score = await self.service.score_candidate(candidate, viewer)

        self.assertLess(score, 0.55)

    async def test_time_decay_keeps_newer_events_ahead_when_other_factors_match(self):
        viewer = self._viewer(current_patient_id=self.patient_id)
        fresh = self._candidate(severity="high", age_minutes=5)
        old = self._candidate(severity="high", age_minutes=180)

        fresh_score = await self.service.score_candidate(fresh, viewer)
        old_score = await self.service.score_candidate(old, viewer)

        self.assertGreater(fresh_score, old_score)


if __name__ == "__main__":
    unittest.main()
