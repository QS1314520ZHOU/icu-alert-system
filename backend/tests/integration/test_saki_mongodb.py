"""S-AKI 真实 MongoDB 集成测试 - motor 异步客户端。"""
from __future__ import annotations

import asyncio
import os
import uuid
import pytest
import pytest_asyncio
from datetime import datetime, timezone, timedelta
from motor.motor_asyncio import AsyncIOMotorClient

TEST_DB = os.environ.get("SMARTCARE_DB_NAME", "icu_alert_saki_test")
TEST_URI = os.environ.get("SMARTCARE_DB_URI", "mongodb://127.0.0.1:27017")

def _assert_safe():
    assert any(k in TEST_DB.lower() for k in ("test","testing","ci")), f"DB必须含test: {TEST_DB}"
    assert TEST_DB.lower() not in ("smartcare","datacenter","icu_alert"), f"不允许生产库: {TEST_DB}"

_assert_safe()
RUN_ID = str(uuid.uuid4())[:8]
PFX = f"SAKI_{RUN_ID}_"
_stats = dict(patients=0,labs=0,vitals=0,drugs=0,crrt=0,cases=0,cohorts=0,audit=0,cleanup=0)

# ---- 在每个测试函数的 event loop 中创建 motor client ----
_client = None
_db = None

@pytest_asyncio.fixture
async def db():
    global _client, _db
    _client = AsyncIOMotorClient(TEST_URI, serverSelectionTimeoutMS=5000)
    await _client.admin.command("ping")
    _db = _client[TEST_DB]
    yield _db
    # 清理: 删除 test_prefix 匹配的数据 + 所有 saki_ 集合数据 + REAL_ 前缀测试数据
    for c in ["patient","labResult","vitalSign","drug","crrt"]:
        r = await _db[c].delete_many({"test_prefix": PFX})
        _stats["cleanup"] += r.deleted_count
    for c in ["saki_cases","saki_cohorts","saki_snapshots","saki_audit_log"]:
        r = await _db[c].delete_many({})
        _stats["cleanup"] += r.deleted_count
    # 清理 REAL_ 前缀的测试数据
    await _db.patient.delete_many({"_id": {"$regex": "^REAL_"}})
    _client.close()
    _client = None
    _db = None

class _DB:
    """包装 motor Database 为 runtime.db.col() 接口。"""
    def __init__(self, db): self._db = db
    def col(self, name): return self._db[name]

def _pid(s): return f"{PFX}{s}"

async def _ins_patient(db, s, **kw):
    pid = _pid(s)
    now = datetime.now(timezone.utc)
    doc = {"_id":pid,"name":f"Test {s}","hisPid":pid,"hisBed":"T-01",
           "dept":"ICU-TEST","hisDept":"ICU-TEST","deptCode":"ICU-TEST",
           "status":"active","sex":kw.pop("sex","M"),"age":kw.pop("age",65),
           "weight":kw.pop("weight",70),"bodyWeight":70,
           "icuAdmissionTime":now-timedelta(days=2),
           "clinicalDiagnosis":kw.pop("clinicalDiagnosis",""),
           "admissionDiagnosis":kw.pop("admissionDiagnosis",""),
           "test_data":True,"test_prefix":PFX}
    doc.update(kw)
    await db["patient"].insert_one(doc); _stats["patients"]+=1; return pid

async def _ins_lab(db, pid, code, val, unit="umol/L", hrs=1):
    await db["labResult"].insert_one({"_id":f"{PFX}l_{pid}_{code}_{hrs}",
        "patientId":pid,"patient_id":pid,"testName":code,"test_code":code,"code":code,
        "result":str(val),"value":val,"unit":unit,
        "reportTime":datetime.now(timezone.utc)-timedelta(hours=hrs),
        "test_data":True,"test_prefix":PFX}); _stats["labs"]+=1

async def _ins_vital(db, pid, code, val, hrs=1):
    await db["vitalSign"].insert_one({"_id":f"{PFX}v_{pid}_{code}_{hrs}",
        "patientId":pid,"patient_id":pid,"param_code":code,"value":val,
        "recordTime":datetime.now(timezone.utc)-timedelta(hours=hrs),
        "test_data":True,"test_prefix":PFX}); _stats["vitals"]+=1

async def _ins_drug(db, pid, name, hrs=6):
    await db["drug"].insert_one({"_id":f"{PFX}d_{pid}_{hrs}",
        "patientId":pid,"patient_id":pid,"drugName":name,"drug_name":name,
        "dose":"1g q8h","route":"IV",
        "startTime":datetime.now(timezone.utc)-timedelta(hours=hrs),
        "test_data":True,"test_prefix":PFX}); _stats["drugs"]+=1

async def _ins_crrt(db, pid, hrs=6):
    await db["crrt"].insert_one({"_id":f"{PFX}c_{pid}",
        "patientId":pid,"patient_id":pid,
        "startTime":datetime.now(timezone.utc)-timedelta(hours=hrs),
        "mode":"CVVHDF","flow_rate":30,
        "test_data":True,"test_prefix":PFX}); _stats["crrt"]+=1

# ==== 1. 连接 ====
class TestConn:
    @pytest.mark.asyncio
    async def test_ping(self, db):
        assert (await db.command("ping"))["ok"] == 1

    @pytest.mark.asyncio
    async def test_insert_find_delete(self, db):
        pid = _pid("C1")
        await db.patient.insert_one({"_id":pid,"x":1,"test_prefix":PFX})
        doc = await db.patient.find_one({"_id":pid})
        assert doc and doc["x"] == 1

# ==== 2. 字段映射 ====
class TestMapping:
    def test_resolve(self):
        from app.services.saki.field_mapping import FieldMappingService
        r = asyncio.get_event_loop().run_until_complete(
            FieldMappingService(None).resolve_field("patient","patient_id"))
        assert "hisPid" in r

# ==== 3. Sepsis ====
class TestSepsis:
    @pytest.mark.asyncio
    async def test_no_infection(self, db):
        pid = await _ins_patient(db,"S001",clinicalDiagnosis="高血压")
        await _ins_lab(db,pid,"cr",70); await _ins_vital(db,pid,"param_nibp_m",80)
        from app.services.saki.sepsis_phenotype import SepsisPhenotypeCalculator
        r = await SepsisPhenotypeCalculator().calculate(_DB(db), pid)
        assert r["is_sepsis"] is False and "sofa_score" in r

    @pytest.mark.asyncio
    async def test_infection(self, db):
        pid = await _ins_patient(db,"S002",clinicalDiagnosis="脓毒症 肺部感染")
        await _ins_lab(db,pid,"cr",180); await _ins_lab(db,pid,"plt",80)
        await _ins_lab(db,pid,"pct",12.0); await _ins_vital(db,pid,"param_nibp_m",55)
        await _ins_drug(db,pid,"美罗培南")
        from app.services.saki.sepsis_phenotype import SepsisPhenotypeCalculator
        r = await SepsisPhenotypeCalculator().calculate(_DB(db), pid)
        assert r["infection_evidence"]["verdict"] in ("supported","possible")

# ==== 4. AKI ====
class TestAKI:
    def test_convert(self):
        from app.services.saki.aki_phenotype import _to_umol_l
        assert _to_umol_l(1.0,"mg/dL") == pytest.approx(88.4,rel=1e-3)
        assert _to_umol_l(100,"umol/L") == 100

    @pytest.mark.asyncio
    async def test_stage0(self, db):
        pid = await _ins_patient(db,"A001")
        await _ins_lab(db,pid,"cr",65,hrs=1); await _ins_lab(db,pid,"cr",62,hrs=48)
        from app.services.saki.aki_phenotype import AKIPhenotypeCalculator
        r = await AKIPhenotypeCalculator().calculate(_DB(db), pid)
        assert r["aki_stage"]==0 and r["creatinine_baseline"] is not None

    @pytest.mark.asyncio
    async def test_stage1(self, db):
        pid = await _ins_patient(db,"A101")
        await _ins_lab(db,pid,"cr",60,hrs=48); await _ins_lab(db,pid,"cr",100,hrs=1)
        from app.services.saki.aki_phenotype import AKIPhenotypeCalculator
        r = await AKIPhenotypeCalculator().calculate(_DB(db), pid)
        assert r["aki_stage"]>=1 and r["creatinine_ratio"]>=1.5

    @pytest.mark.asyncio
    async def test_stage3_crrt(self, db):
        pid = await _ins_patient(db,"A301")
        await _ins_lab(db,pid,"cr",80); await _ins_crrt(db,pid)
        from app.services.saki.aki_phenotype import AKIPhenotypeCalculator
        r = await AKIPhenotypeCalculator().calculate(_DB(db), pid)
        assert r["aki_stage"]==3

    @pytest.mark.asyncio
    async def test_mgdl(self, db):
        pid = await _ins_patient(db,"A401")
        await _ins_lab(db,pid,"cr",0.8,"mg/dL",48); await _ins_lab(db,pid,"cr",3.5,"mg/dL",1)
        from app.services.saki.aki_phenotype import AKIPhenotypeCalculator
        r = await AKIPhenotypeCalculator().calculate(_DB(db), pid)
        assert r["aki_stage"]>=2 and r["creatinine_current"]>=300

# ==== 5. S-AKI ====
class TestSAKI:
    @pytest.mark.asyncio
    async def test_identify(self, db):
        pid = await _ins_patient(db,"SA001",clinicalDiagnosis="脓毒症 肺部感染")
        await _ins_lab(db,pid,"cr",60,hrs=48); await _ins_lab(db,pid,"cr",180,hrs=1)
        await _ins_lab(db,pid,"pct",15.0); await _ins_vital(db,pid,"param_nibp_m",55)
        await _ins_drug(db,pid,"美罗培南")
        from app.services.saki.saki_identifier import SAKICaseIdentifier
        r = await SAKICaseIdentifier().identify(_DB(db), pid)
        _stats["cases"]+=1
        assert "is_saki" in r and "sepsis_phenotype" in r and "aki_phenotype" in r

    @pytest.mark.asyncio
    async def test_persisted(self, db):
        pid = await _ins_patient(db,"SA002",clinicalDiagnosis="脓毒症 腹腔感染")
        await _ins_lab(db,pid,"cr",55,hrs=48); await _ins_lab(db,pid,"cr",200,hrs=1)
        await _ins_lab(db,pid,"pct",20.0); await _ins_vital(db,pid,"param_nibp_m",50)
        await _ins_drug(db,pid,"美罗培南")
        from app.services.saki.saki_identifier import SAKICaseIdentifier
        await SAKICaseIdentifier().identify(_DB(db), pid); _stats["cases"]+=1
        case = await db.saki_cases.find_one({"patient_id":pid})
        assert case is not None and case["patient_id"]==pid

    def test_temporal_out(self):
        from app.services.saki.saki_identifier import SAKICaseIdentifier
        r = SAKICaseIdentifier()._assess_temporal_association(
            {"calc_time":datetime(2024,1,1,tzinfo=timezone.utc)},
            {"calc_time":datetime(2024,3,1,tzinfo=timezone.utc)})
        assert r["associated"] is False

# ==== 6. 队列 ====
class TestCohort:
    @pytest.mark.asyncio
    async def test_build_delete(self, db):
        from app.services.saki.cohort_builder import SAKICohortBuilder
        b = SAKICohortBuilder()
        c = await b.build_cohort(_DB(db),{"is_saki":True},f"C_{RUN_ID}","test")
        _stats["cohorts"]+=1
        assert await db.saki_cohorts.find_one({"cohort_id":c["cohort_id"]}) is not None
        ok = await b.delete_cohort(_DB(db), c["cohort_id"])
        assert ok is True
        assert await db.saki_cohorts.find_one({"cohort_id":c["cohort_id"]}) is None

# ==== 7. 审计 ====
class TestAudit:
    @pytest.mark.asyncio
    async def test_log_find(self, db):
        from app.services.saki.audit_service import SAKIAuditService
        eid = await SAKIAuditService().log_event(_DB(db),"act","res","r1","u",{"k":"v"})
        _stats["audit"]+=1
        ev = await db.saki_audit_log.find_one({"event_id":eid})
        assert ev is not None and ev["action"]=="act"

# ==== 8. 清理 ====
class TestCleanup:
    @pytest.mark.asyncio
    async def test_residue(self, db):
        for c in ["patient","labResult","vitalSign","drug","crrt",
                   "saki_cases","saki_cohorts","saki_snapshots","saki_audit_log"]:
            n = await db[c].count_documents({"test_prefix":PFX})
            assert n==0, f"{c} 残留 {n}"

    @pytest.mark.asyncio
    async def test_non_test_preserved(self, db):
        await db.patient.insert_one({"_id":"REAL_KEEP","keep":True,"test_data":False})
        await db.patient.delete_many({"test_prefix":PFX})
        assert await db.patient.find_one({"_id":"REAL_KEEP"}) is not None
        await db.patient.delete_one({"_id":"REAL_KEEP"})

def pytest_sessionfinish(s,e):
    print(f"\n{'='*50}\nS-AKI 集成测试 (run={RUN_ID})")
    for k,v in _stats.items(): print(f"  {k:>10}: {v}")
    print(f"{'='*50}")

