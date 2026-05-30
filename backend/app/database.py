"""
ICU智能协同工作台 - 数据库连接管理
使用 PyMongo 4.16 原生 AsyncMongoClient（Motor 已废弃）
"""
import logging
from pymongo import AsyncMongoClient
from pymongo.errors import OperationFailure
import redis.asyncio as aioredis

logger = logging.getLogger("icu-alert")


class DatabaseManager:
    def __init__(self, config):
        self.config = config
        self.smartcare_client: AsyncMongoClient | None = None
        self.datacenter_client: AsyncMongoClient | None = None
        self.smartcare_db = None
        self.datacenter_db = None
        self.redis = None

    async def _connect_mongo(self, name: str, uri: str, db_name: str, host: str, port: int):
        client = AsyncMongoClient(uri)
        db = client[db_name]
        try:
            await client.admin.command("ping")
            return client, db
        except Exception as e:
            msg = str(e).lower()
            if "auth" in msg or "authentication" in msg or "not authorized" in msg:
                logger.warning(f"⚠️ {name} 认证失败，尝试无认证连接...")
                no_auth_uri = f"mongodb://{host}:{port}/"
                client = AsyncMongoClient(no_auth_uri)
                db = client[db_name]
                await client.admin.command("ping")
                return client, db
            raise

    async def connect(self):
        """连接所有数据库"""

        # 兼容 database 和 databases 两种YAML写法
        db_cfg = self.config.yaml_cfg.get("database", {})
        if not db_cfg:
            db_cfg = self.config.yaml_cfg.get("databases", {})

        smartcare_cfg = db_cfg.get("smartcare", {})
        datacenter_cfg = db_cfg.get("datacenter", {})

        # ---- SmartCare (ICU专用库，读写) ----
        smartcare_db_name = smartcare_cfg.get("db_name") or smartcare_cfg.get("database", "SmartCare")
        logger.info(f"正在连接 SmartCare ({smartcare_db_name})...")

        self.smartcare_client, self.smartcare_db = await self._connect_mongo(
            "SmartCare",
            self.config.smartcare_uri,
            smartcare_db_name,
            self.config.settings.SMARTCARE_DB_HOST,
            self.config.settings.SMARTCARE_DB_PORT,
        )
        logger.info("✅ SmartCare 数据库连接成功")

        # ---- DataCenter (HIS/LIS，只读) ----
        datacenter_db_name = datacenter_cfg.get("db_name") or datacenter_cfg.get("database", "DataCenter")
        logger.info(f"正在连接 DataCenter ({datacenter_db_name})...")

        self.datacenter_client, self.datacenter_db = await self._connect_mongo(
            "DataCenter",
            self.config.datacenter_uri,
            datacenter_db_name,
            self.config.settings.DATACENTER_DB_HOST,
            self.config.settings.DATACENTER_DB_PORT,
        )
        logger.info("✅ DataCenter 数据库连接成功")

        # ---- Redis ----
        try:
            self.redis = aioredis.from_url(
                self.config.redis_url,
                decode_responses=True
            )
            await self.redis.ping()
            logger.info("✅ Redis 连接成功")
        except Exception as e:
            logger.warning(f"⚠️ Redis 连接失败（非致命）: {e}")
            self.redis = None

        # ---- 打印统计 ----
        await self._print_stats()

        # ---- 创建预警系统索引 ----
        await self._create_indexes()

    async def _print_stats(self):
        """打印关键统计信息"""
        try:
            patient_count = await self.col("patient").count_documents(
                {
                    "$or": [
                        {"status": {"$nin": ["discharged", "invalid", "invaild"]}},
                        {"status": {"$exists": False}},
                    ]
                }
            )
            logger.info(f"📊 当前在院患者: {patient_count}")
        except Exception as e:
            logger.warning(f"查询患者数失败: {e}")

        try:
            device_count = await self.col("deviceBind").count_documents(
                {"unBindTime": None}
            )
            logger.info(f"📊 当前绑定设备: {device_count}")
        except Exception as e:
            logger.warning(f"查询设备数失败: {e}")

        try:
            online_count = await self.col("deviceOnline").count_documents(
                {"isConnected": True}
            )
            logger.info(f"📊 当前在线设备: {online_count}")
        except Exception as e:
            logger.warning(f"查询在线设备数失败: {e}")

        try:
            exam_count = await self.dc_col("VI_ICU_EXAM_ITEM").count_documents({})
            logger.info(f"📊 检验项总量: {exam_count}")
        except Exception as e:
            logger.warning(f"查询检验项数失败: {e}")

    async def _create_indexes(self):
        """为预警系统创建必要索引"""
        try:
            async def ensure_ttl_index(collection, keys, *, name: str, expire_after_seconds: int) -> None:
                try:
                    await collection.create_index(keys, name=name, expireAfterSeconds=expire_after_seconds)
                except OperationFailure as exc:
                    text = str(exc)
                    if "IndexOptionsConflict" not in text and "already exists with different options" not in text:
                        raise
                    await collection.drop_index(name)
                    await collection.create_index(keys, name=name, expireAfterSeconds=expire_after_seconds)

            # 预警记录索引
            alert_col = self.col("alert_records")
            await alert_col.create_index([("patient_id", 1), ("created_at", -1)])
            await alert_col.create_index([("alert_type", 1), ("severity", 1)])
            await alert_col.create_index([("is_active", 1)])
            await alert_col.create_index([("viewed_at", 1), ("acknowledged_at", 1)])
            await alert_col.create_index([("actionability_score", -1), ("created_at", -1)])

            patient_col = self.col("patient")
            await self.col("bGATemp").create_index([("mrn", 1), ("inputTime", -1)])
            await patient_col.create_index([("status", 1), ("deptCode", 1)])
            await patient_col.create_index([("status", 1), ("departmentCode", 1)])
            await patient_col.create_index([("status", 1), ("hisDept", 1)])
            await patient_col.create_index([("status", 1), ("dept", 1)])
            await patient_col.create_index([("hisPid", 1)])

            account_col = self.col("account")
            await account_col.create_index([("userName", 1)])
            await account_col.create_index([("username", 1)])
            await account_col.create_index([("deptCode", 1)])
            await account_col.create_index([("departmentCode", 1)])

            outcome_col = self.col("alert_outcomes")
            await outcome_col.create_index([("alert_id", 1)], unique=True)
            await outcome_col.create_index([("patient_id", 1), ("fired_at", -1)])
            await outcome_col.create_index([("scanner_name", 1), ("fired_at", -1)])
            await outcome_col.create_index([("disposition", 1), ("fired_at", -1)])
            await outcome_col.create_index([("manual_review_required", 1), ("updated_at", -1)])

            await self.col("model_calibration_runs").create_index([("job_type", 1), ("created_at", -1)])
            await self.col("adaptive_threshold_reviews").create_index([("scanner_name", 1), ("status", 1)], unique=True)

            # 预警规则索引
            rule_col = self.col("alert_rules")
            await rule_col.create_index([("rule_id", 1)], unique=True)
            await rule_col.create_index([("enabled", 1), ("category", 1)])

            # 字段映射索引
            mapping_col = self.col("field_mapping")
            await mapping_col.create_index(
                [("source_code", 1), ("source_name", 1)], unique=True
            )
            await mapping_col.create_index([("standard_concept", 1)])
            await self.col("runtime_configs").create_index([("key", 1)], unique=True)
            await self.col("runtime_configs").create_index([("updated_at", -1)])
            await self.col("runtime_config_versions").create_index([("key", 1), ("version", -1)])
            await self.col("runtime_config_versions").create_index([("created_at", -1)])
            # 评分记录索引
            score_col = self.col("score")
            await score_col.create_index(
                [("patient_id", 1), ("score_type", 1), ("calc_time", -1)]
            )
            await score_col.create_index(
                [("pid", 1), ("scoreType", 1), ("time", -1)]
            )

            # 护理提醒索引
            reminder_col = self.col("nurse_reminders")
            await reminder_col.create_index(
                [("patient_id", 1), ("score_type", 1), ("is_active", 1)]
            )
            await reminder_col.create_index(
                [("patient_id", 1), ("is_active", 1), ("due_at", 1)]
            )

            # 床旁数据索引（高频查询）
            bedside_col = self.col("bedside")
            await bedside_col.create_index([("pid", 1), ("code", 1), ("time", -1)])
            await bedside_col.create_index([("pid", 1), ("time", -1)])

            # 设备数据索引
            device_cap_col = self.col("deviceCap")
            await device_cap_col.create_index([("deviceID", 1), ("code", 1), ("time", -1)])
            device_bind_col = self.col("deviceBind")
            await device_bind_col.create_index([("pid", 1), ("unBindTime", -1)])

            # 用药执行索引
            drug_col = self.col("drugExe")
            await drug_col.create_index([("pid", 1), ("executeTime", -1)])
            await drug_col.create_index([("pid", 1), ("drugName", 1)])

            # 护理记录索引
            nurse_col = self.col("nurseRecords")
            await nurse_col.create_index([("pid", 1), ("recordTime", -1)])
            await nurse_col.create_index([("pid", 1), ("created_at", -1)])

            # 告警记录补充索引
            await alert_col.create_index([("rule_id", 1), ("patient_id", 1), ("created_at", -1)])

            # Bundle 合规每日汇总索引
            bundle_daily_col = self.col("bundle_compliance_daily")
            await bundle_daily_col.create_index([("date", 1), ("dept", 1), ("deptCode", 1)], unique=True)

            # AI 监控索引
            ai_log_col = self.col("ai_monitor_logs")
            await ai_log_col.create_index([("created_at", -1), ("module", 1)])
            await ai_log_col.create_index([("module", 1), ("success", 1), ("created_at", -1)])

            ai_daily_col = self.col("ai_monitor_daily_stats")
            await ai_daily_col.create_index([("date", 1), ("module", 1)], unique=True)

            ai_alert_col = self.col("ai_monitor_alerts")
            await ai_alert_col.create_index([("date", 1), ("module", 1), ("alert_code", 1)], unique=True)
            await ai_alert_col.create_index([("is_active", 1), ("updated_at", -1)])

            integrated_report_col = self.col("integrated_risk_reports")
            await integrated_report_col.create_index([("patient_id", 1), ("created_at", -1)])
            await integrated_report_col.create_index([("risk_level", 1), ("created_at", -1)])

            research_runtime_col = self.col("research_runtime_checks")
            await research_runtime_col.create_index([("date", 1)], unique=True)
            await research_runtime_col.create_index([("checked_at", -1)])

            research_artifact_col = self.col("research_artifacts")
            await research_artifact_col.create_index([("created_by", 1), ("created_at", -1)])
            await research_artifact_col.create_index([("artifact_type", 1), ("created_at", -1)])
            await research_artifact_col.create_index([("source_task_id", 1), ("created_at", -1)])

            followup_case_col = self.col("followup_cases")
            await followup_case_col.create_index([("case_id", 1)], unique=True)
            await followup_case_col.create_index([("patient_id", 1), ("source_module", 1)], unique=True)
            await followup_case_col.create_index([("status", 1), ("priority", 1), ("updated_at", -1)])

            followup_task_col = self.col("followup_tasks")
            await followup_task_col.create_index([("task_id", 1)], unique=True)
            await followup_task_col.create_index([("patient_id", 1), ("status", 1), ("created_at", -1)])
            await followup_task_col.create_index([("case_id", 1), ("created_at", -1)])

            rehab_referral_col = self.col("rehab_referrals")
            await rehab_referral_col.create_index([("referral_id", 1)], unique=True)
            await rehab_referral_col.create_index([("patient_id", 1), ("status", 1), ("created_at", -1)])
            await rehab_referral_col.create_index([("case_id", 1), ("created_at", -1)])

            await self.col("audit_logs").create_index([("module", 1), ("action", 1), ("created_at", -1)])
            await self.col("ai_generated_content_logs").create_index([("module", 1), ("patient_id", 1), ("generated_at", -1)])
            await self.col("rounding_export_tasks").create_index([("task_id", 1)], unique=True)
            await self.col("airway_records").create_index([("patient_id", 1), ("recorded_at", -1)])
            await self.col("airway_plans").create_index([("patient_id", 1), ("updated_at", -1)])
            await self.col("clinical_tasks").create_index([("task_id", 1)], unique=True)
            await self.col("clinical_tasks").create_index([("patient_id", 1), ("status", 1), ("updated_at", -1)])
            await self.col("clinical_tasks").create_index([("patient_id", 1), ("status", 1), ("priority", -1), ("updated_at", -1)])
            await self.col("clinical_tasks").create_index([("module", 1), ("status", 1), ("updated_at", -1)])
            await self.col("nutrition_tasks").create_index([("task_id", 1)], unique=True)
            await self.col("nutrition_tasks").create_index([("patient_id", 1), ("status", 1), ("updated_at", -1)])
            await self.col("nutrition_detail_cache").create_index([("patient_id", 1)], unique=True)
            await self.col("nutrition_detail_cache").create_index([("updated_at", -1)])
            await self.col("research_projects").create_index([("project_id", 1)], unique=True)
            await self.col("research_topic_suggestions").create_index([("generated_at", -1)])
            await self.col("omop_export_tasks").create_index([("task_id", 1)], unique=True)
            await self.col("clinical_trials").create_index([("trial_id", 1)], unique=True)
            await self.col("clinical_trials").create_index([("status", 1), ("updated_at", -1)])
            await self.col("clinical_trial_candidates").create_index([("candidate_id", 1)], unique=True)
            await self.col("clinical_trial_candidates").create_index([("patient_id", 1), ("updated_at", -1)])
            scanner_runs_col = self.col("scanner_runs")
            await scanner_runs_col.create_index([("scanner_name", 1), ("created_at", -1)])
            await ensure_ttl_index(
                scanner_runs_col,
                [("created_at", 1)],
                name="scanner_runs_created_at_ttl_14d",
                expire_after_seconds=14 * 24 * 3600,
            )
            llm_call_col = self.col("llm_call_logs")
            await llm_call_col.create_index([("created_at", -1)])
            await llm_call_col.create_index([("cache_key", 1), ("created_at", -1)])
            await ensure_ttl_index(
                llm_call_col,
                [("created_at", 1)],
                name="llm_call_logs_created_at_ttl_14d",
                expire_after_seconds=14 * 24 * 3600,
            )

            # 临床文书索引
            draft_col = self.col("clinical_document_drafts")
            await draft_col.create_index([("patient_id", 1), ("created_at", -1)])
            await draft_col.create_index([("status", 1), ("created_at", -1)])
            version_col = self.col("clinical_document_versions")
            await version_col.create_index([("draft_id", 1), ("version_no", -1)])

            logger.info("✅ 预警系统索引创建完成")
            await self._seed_default_rules()
        except Exception as e:
            logger.warning(f"创建索引时出错（非致命）: {e}")

    async def _seed_default_rules(self):
        """插入默认预警规则（如果集合为空）"""
        try:
            col = self.col("alert_rules")
            count = await col.count_documents({})
            if count > 0:
                return

            default_rules = [
                {
                    "rule_id": "VITAL_HR_HIGH",
                    "name": "心率过快",
                    "category": "vital_signs",
                    "parameter": "param_HR",
                    "condition": {"operator": ">", "threshold": 130},
                    "severity": "warning",
                    "enabled": True,
                },
                {
                    "rule_id": "VITAL_HR_CRIT_HIGH",
                    "name": "心率极速",
                    "category": "vital_signs",
                    "parameter": "param_HR",
                    "condition": {"operator": ">", "threshold": 150},
                    "severity": "critical",
                    "enabled": True,
                },
                {
                    "rule_id": "VITAL_HR_LOW",
                    "name": "心率过缓",
                    "category": "vital_signs",
                    "parameter": "param_HR",
                    "condition": {"operator": "<", "threshold": 50},
                    "severity": "warning",
                    "enabled": True,
                },
                {
                    "rule_id": "VITAL_SPO2_LOW",
                    "name": "血氧饱和度偏低",
                    "category": "vital_signs",
                    "parameter": "param_spo2",
                    "condition": {"operator": "<", "threshold": 92},
                    "severity": "warning",
                    "enabled": True,
                },
                {
                    "rule_id": "VITAL_SPO2_CRIT",
                    "name": "血氧饱和度危急",
                    "category": "vital_signs",
                    "parameter": "param_spo2",
                    "condition": {"operator": "<", "threshold": 85},
                    "severity": "critical",
                    "enabled": True,
                },
                {
                    "rule_id": "VITAL_TEMP_HIGH",
                    "name": "高热",
                    "category": "vital_signs",
                    "parameter": "param_T",
                    "condition": {"operator": ">", "threshold": 39.0},
                    "severity": "warning",
                    "enabled": True,
                },
                {
                    "rule_id": "VITAL_TEMP_CRIT",
                    "name": "超高热",
                    "category": "vital_signs",
                    "parameter": "param_T",
                    "condition": {"operator": ">", "threshold": 40.5},
                    "severity": "critical",
                    "enabled": True,
                },
                {
                    "rule_id": "VITAL_SBP_HIGH",
                    "name": "收缩压过高",
                    "category": "vital_signs",
                    "parameter": "param_nibp_s",
                    "condition": {"operator": ">", "threshold": 180},
                    "severity": "warning",
                    "enabled": True,
                },
                {
                    "rule_id": "VITAL_SBP_LOW",
                    "name": "收缩压过低",
                    "category": "vital_signs",
                    "parameter": "param_nibp_s",
                    "condition": {"operator": "<", "threshold": 80},
                    "severity": "critical",
                    "enabled": True,
                },
                {
                    "rule_id": "VITAL_RR_HIGH",
                    "name": "呼吸频率过快",
                    "category": "vital_signs",
                    "parameter": "param_resp",
                    "condition": {"operator": ">", "threshold": 30},
                    "severity": "warning",
                    "enabled": True,
                },
                {
                    "rule_id": "VITAL_RR_LOW",
                    "name": "呼吸频率过缓",
                    "category": "vital_signs",
                    "parameter": "param_resp",
                    "condition": {"operator": "<", "threshold": 8},
                    "severity": "critical",
                    "enabled": True,
                },
            ]

            await col.insert_many(default_rules)
            logger.info(f"✅ 已插入 {len(default_rules)} 条默认预警规则")
        except Exception as e:
            logger.warning(f"插入默认预警规则失败（非致命）: {e}")

    def col(self, name: str):
        """获取 SmartCare 集合"""
        return self.smartcare_db[name]

    def dc_col(self, name: str):
        """获取 DataCenter 集合"""
        return self.datacenter_db[name]

    async def disconnect(self):
        """关闭所有连接"""
        if self.smartcare_client:
            res = self.smartcare_client.close()
            if hasattr(res, "__await__"):
                await res
        if self.datacenter_client:
            res = self.datacenter_client.close()
            if hasattr(res, "__await__"):
                await res
        if self.redis:
            await self.redis.close()
        logger.info("🔌 所有数据库连接已关闭")
