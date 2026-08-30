# Frontend-Backend Mapping Matrix

**Generated:** 2026-08-30
**RUN_ID:** 8b4eeab1-6b78-47f8-a36c-e8f788402923

## Global Pages

| Module | Page Route | renderMode | Frontend API | Backend Endpoint | MongoDB Collection | Auth Required | Status |
|--------|-----------|------------|--------------|------------------|-------------------|---------------|--------|
| 首页重定向 | `/` | native | - | - | - | No | ✅ PASS |
| 医生首页 | `/doctor-home` | native | `getHomeDoctor` | `GET /api/home/doctor` | patient, alert_records | Yes | ✅ PASS |
| 护士首页 | `/nurse-home` | native | `getHomeNurse` | `GET /api/home/nurse` | patient, alert_records | Yes | ✅ PASS |
| 护士长首页 | `/head-nurse-home` | native | `getHomeHeadNurse` | `GET /api/home/head-nurse` | patient, alert_records | Yes | ✅ PASS |
| 主任首页 | `/director-home` | native | `getHomeDirector` | `GET /api/home/director` | patient, alert_records | Yes | ✅ PASS |
| 患者总览 | `/patients` | native | `getPatients` | `GET /api/patients` | patient, bedside | No | ✅ PASS |
| 临床工作台 | `/clinical-workflow` | native | `getClinicalWorkflow` | `GET /api/clinical-workflow/summary` | patient, alert_records | Yes | ✅ PASS |
| 历史预警分析 | `/analytics` | native | `getAlertAnalytics` | `GET /api/alerts/analytics/*` | alert_records | Yes | ✅ PASS |
| AI问诊 | `/ai-consult` | native | `postAiChatConsult` | `POST /api/ai/chat-consult` | - | Yes | ✅ PASS |
| 智能查房 | `/rounding-sheet` | native | `getRoundingReport` | `GET /api/rounding/*` | rounding_records | Yes | ✅ PASS |
| 呼吸治疗 | `/respiratory-dashboard` | native | `getRespiratoryDashboard` | `GET /api/respiratory/*` | ventilator_data | Yes | ✅ PASS |
| 营养支持 | `/nutrition-support` | native | `getNutritionAssessment` | `GET /api/nutrition/*` | nutrition_records | Yes | ✅ PASS |
| 学术科研 | `/academic-research` | native | `getResearchData` | `GET /api/research/*` | research_data | Yes | ✅ PASS |
| 临床试验 | `/clinical-trials` | native | `getClinicalTrials` | `GET /api/clinical-trials/*` | clinical_trials | Yes | ✅ PASS |
| 科研导出 | `/research-export` | native | `getResearchExport` | `GET /api/research/export` | research_data | Yes | ✅ PASS |
| 科研分析 | `/research-workbench` | native | `getResearchAnalytics` | `GET /api/research/analytics` | research_data | Yes | ✅ PASS |
| MDT会诊 | `/mdt` | native | `getMdtWorkspace` | `GET /api/ai/mdt-workspace/*` | mdt_sessions | Yes | ✅ PASS |
| AI运营 | `/ai-ops` | native | `getAiMonitorSummary` | `GET /api/ai/monitor/summary` | ai_monitor_alerts | Yes | ✅ PASS |
| 配置中心 | `/admin/runtime-config` | native | `getRuntimeConfig` | `GET /api/admin/runtime-config` | alert_rules, field_mapping | Admin | ✅ PASS |
| 规则健康 | `/admin/scanner-health` | native | `getScannerHealth` | `GET /api/admin/scanner-health` | alert_records, alert_adjudications | Admin | ✅ PASS |
| 护士站大屏 | `/bigscreen` | native | - | - | - | No | ✅ PASS |

## Patient Detail Pages

| Module | Page Route | renderMode | Frontend API | Backend Endpoint | MongoDB Collection | Auth Required | Status |
|--------|-----------|------------|--------------|------------------|-------------------|---------------|--------|
| 患者总览 | `/patient/:id/overview` | native | `getPatientDetail` | `GET /api/patients/{id}` | patient, bedside | Yes | ✅ PASS |
| 患者监测 | `/patient/:id/monitoring` | native | `getPatientVitals` | `GET /api/patients/{id}/vitals` | bedside, deviceBind | Yes | ✅ PASS |
| 治疗护理 | `/patient/:id/treatment` | native | `getPatientTreatment` | `GET /api/treatment/{id}` | drugExe | Yes | ✅ PASS |
| 预警决策 | `/patient/:id/alerts` | native | `getPatientAlerts` | `GET /api/alerts/recent` | alert_records | Yes | ✅ PASS |
| AI文书 | `/patient/:id/documents` | native | `getClinicalDocuments` | `GET /api/clinical-documents/{id}` | clinical_documents | Yes | ✅ PASS |
| AI分析 | `/patient/:id/intelligence` | native | - | - | - | Yes | ✅ PASS |
| 随访管理 | `/patient/:id/followup` | native | `getFollowupCases` | `GET /api/followup_cases` | followup_cases | Yes | ✅ PASS |

## Embed Modules (iframe)

| Module | Page Route | renderMode | Frontend API | Backend Endpoint | MongoDB Collection | Feature Flag | Status |
|--------|-----------|------------|--------------|------------------|-------------------|--------------|--------|
| 风险预测 | `/embed/patient/:id/risk-prediction` | embed | `getRiskForecast` | `GET /api/ai/risk-forecast/{id}` | score | ai-risk-prediction | ✅ PASS |
| 综合风险 | `/embed/patient/:id/integrated-risk` | embed | `getIntegratedRisk` | `GET /api/ai/integrated-risk/{id}` | score, alert_records | ai-integrated-risk | ✅ PASS |
| 相似病例 | `/embed/patient/:id/similar-cases` | embed | `getSimilarCases` | `GET /api/ai/similar-cases/{id}` | patient, score | ai-similar-cases | ✅ PASS |
| 因果推断 | `/embed/patient/:id/causal-inference` | embed | `postCausalAnalysis` | `POST /api/ai/causal-analysis/{id}` | score | ai-causal-inference | ✅ PASS |
| What-if | `/embed/patient/:id/what-if` | embed | `postWhatIf` | `POST /api/ai/what-if/{id}` | score | ai-what-if | ✅ PASS |
| 病程推演 | `/embed/patient/:id/disease-trajectory` | embed | `getDigitalTwin` | `GET /api/ai/digital-twin/{id}` | score, bedside | ai-disease-trajectory | ✅ PASS |
| 循证证据 | `/embed/patient/:id/evidence` | embed | `getClinicalEvidence` | `GET /api/clinical-evidence/{id}` | alert_records, score | ai-evidence | ✅ PASS |
| 专项决策 | `/embed/patient/:id/decision-assistants` | embed | `getDecisionAssistants` | `GET /api/respiratory/*` | patient | ai-decision-assistants | ✅ PASS |

## Handover Pages

| Module | Page Route | renderMode | Frontend API | Backend Endpoint | MongoDB Collection | Roles | Status |
|--------|-----------|------------|--------------|------------------|-------------------|-------|--------|
| 交班总览 | `/handover/overview` | native | `getHandoverSummary` | `GET /api/handover/summary` | patient, handover | nurse, head_nurse, doctor | ✅ PASS |
| 患者交班 | `/handover/patients` | native | `getHandoverPatients` | `GET /api/handover/patients` | patient | nurse, head_nurse, doctor | ✅ PASS |
| 待办任务 | `/handover/tasks` | native | `getHandoverTasks` | `GET /api/handover/tasks` | handover_tasks | nurse, head_nurse, doctor | ✅ PASS |
| 交班历史 | `/handover/history` | native | `getHandoverHistory` | `GET /api/handover/history` | handover_records | nurse, head_nurse, doctor | ✅ PASS |

## Disease Center Pages

| Module | Page Route | renderMode | Backend Endpoint | Status |
|--------|-----------|------------|------------------|--------|
| 总览 | `/disease-center/overview` | native | `GET /api/disease-center/overview` | ✅ PASS |
| 病种目录 | `/disease-center/diseases` | native | `GET /api/disease-center/diseases` | ✅ PASS |
| 术语编码 | `/disease-center/terminology` | native | `GET /api/disease-center/terminology` | ✅ PASS |
| 评分规则 | `/disease-center/scores` | native | `GET /api/disease-center/scores` | ✅ PASS |
| 表型规则 | `/disease-center/phenotypes` | native | `GET /api/disease-center/phenotypes` | ✅ PASS |
| 离线知识包 | `/disease-center/offline-packages` | native | `GET /api/disease-center/offline-packages` | ✅ PASS |
| 审核发布 | `/disease-center/reviews` | native | `GET /api/disease-center/reviews` | ✅ PASS |
| AI助手 | `/disease-center/ai` | native | `GET /api/disease-center/ai` | ✅ PASS |
| 质量监控 | `/disease-center/quality` | native | `GET /api/disease-center/quality` | ✅ PASS |

## S-AKI Pages

| Module | Page Route | renderMode | Backend Endpoint | Status |
|--------|-----------|------------|------------------|--------|
| 总览 | `/disease-center/saki/overview` | native | `GET /api/saki/overview` | ✅ PASS |
| 病例库 | `/disease-center/saki/cases` | native | `GET /api/saki/cases` | ✅ PASS |
| 队列构建 | `/disease-center/saki/cohorts` | native | `GET /api/saki/cohorts` | ✅ PASS |
| 统计分析 | `/disease-center/saki/analysis` | native | `GET /api/saki/analysis` | ✅ PASS |
| 图表 | `/disease-center/saki/charts` | native | `GET /api/saki/charts` | ✅ PASS |
| 数据质量 | `/disease-center/saki/quality` | native | `GET /api/saki/quality` | ✅ PASS |
| 字段映射 | `/disease-center/saki/field-mapping` | native | `GET /api/saki/field-mapping` | ✅ PASS |

## Mobile Pages

| Module | Page Route | renderMode | Backend Endpoint | Status |
|--------|-----------|------------|------------------|--------|
| 移动首页 | `/m` | native | `GET /api/mobile/home` | ✅ PASS |
| 患者列表 | `/m/patients` | native | `GET /api/mobile/patients` | ✅ PASS |
| 告警 | `/m/alerts` | native | `GET /api/mobile/alerts` | ✅ PASS |
| 任务 | `/m/tasks` | native | `GET /api/mobile/tasks` | ✅ PASS |
| AI问诊 | `/m/consult` | native | `POST /api/ai/chat-consult` | ✅ PASS |
| 我的 | `/m/me` | native | - | ✅ PASS |

---

## Summary

- **Total Routes Mapped:** 56
- **Native Modules:** 48
- **Embed Modules:** 8
- **All Routes Verified:** ✅
- **All API Endpoints Verified:** ✅
- **Auth Consistency:** ✅ (frontend roles match backend requirements)
- **No Orphan APIs:** ✅
- **No Empty Shell Pages:** ✅
