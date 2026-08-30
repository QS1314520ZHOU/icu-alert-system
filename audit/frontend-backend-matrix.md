# Frontend-Backend Mapping Matrix

| Module | Page Route | renderMode | Frontend API | Backend Endpoint | MongoDB Collection | Permission | Test Status |
|--------|-----------|------------|--------------|-----------------|-------------------|------------|-------------|
| Auth | /login | native | POST /api/auth/login | /api/auth/login | users | public | PASS |
| Doctor Home | /doctor-home | native | getDoctorHome | /api/home/doctor | patient, alert_records | doctor | PASS |
| Nurse Home | /nurse-home | native | getNurseHome | /api/home/nurse | patient, alert_records | nurse | PASS |
| Head Nurse Home | /head-nurse-home | native | getHeadNurseHome | /api/home/head-nurse | patient, alert_records | head_nurse | PASS |
| Director Home | /director-home | native | getDirectorHome | /api/home/director | patient, alert_records | director | PASS |
| Patient List | /patients | native | getPatients | /api/patients | patient | all | PASS |
| Patient Overview | /patient/:id/overview | native | getPatientDetail | /api/patients/{id} | patient | all | PASS |
| Patient Monitoring | /patient/:id/monitoring | native | getPatientVitalsTrend | /api/patients/{id}/vitals/trend | bedside, deviceCap | all | PASS |
| Patient Treatment | /patient/:id/treatment | native | getPatientDrugs | /api/patients/{id}/drugs | drugExe | all | PASS |
| Patient Alerts | /patient/:id/alerts | native | getPatientAlerts | /api/patients/{id}/alerts | alert_records | all | PASS |
| Patient Documents | /patient/:id/documents | native | generateAiDocument | /api/ai/documents/{id} | clinical_document_drafts | doctor,nurse | PASS |
| Patient Followup | /patient/:id/followup | native | getPatientFollowupCase | /api/followup_cases/patients/{id} | followup_cases | doctor,nurse | PASS |
| Risk Prediction | /embed/patient/:id/risk-prediction | embed | getAiRiskForecast | /api/ai/risk-forecast/{id} | score | doctor,nurse | PASS |
| Integrated Risk | /embed/patient/:id/integrated-risk | embed | getAiIntegratedRiskReport | /api/ai/integrated-risk/{id} | integrated_risk_reports | doctor,nurse | PASS |
| Similar Cases | /embed/patient/:id/similar-cases | embed | getPatientSimilarCaseOutcomes | /api/patients/{id}/similar-case-outcomes | patient | doctor,researcher | PASS |
| Causal Inference | /embed/patient/:id/causal-inference | embed | postAiCausalAnalysis | /api/ai/causal-analysis/{id} | - | doctor | BLOCKED |
| What-if | /embed/patient/:id/what-if | embed | postAiWhatIfSimulation | /api/ai/what-if/{id} | - | doctor | BLOCKED |
| Disease Trajectory | /embed/patient/:id/disease-trajectory | embed | - | - | - | doctor | BLOCKED |
| Evidence | /embed/patient/:id/evidence | embed | getPatientRAGSearch | /api/patients/{id}/rag-search | - | all | PASS |
| Clinical Workflow | /clinical-workflow | native | getClinicalRoleHome | /api/clinical-workflow/role-home | clinical_tasks | all | PASS |
| Handover | /handover | native | - | /api/handover/overview | handover_documents | nurse,doctor | PASS |
| AI Consult | /ai-consult | native | postAiConsultChat | /api/ai/chat-consult | - | all | PASS |
| Rounding Sheet | /rounding-sheet | native | - | /api/rounding/reports | rounding_report_versions | all | PASS |
| Respiratory | /respiratory-dashboard | native | - | /api/respiratory/dashboard | score, patient | all | PASS |
| Nutrition | /nutrition-support | native | - | /api/nutrition/dashboard | nutrition_tasks | all | PASS |
| Analytics | /analytics | native | getAlertStats | /api/alerts/stats | alert_records | all | PASS |
| Disease Center | /disease-center | native | - | /api/disease-center/diseases | diseaseDiagnosis | all | PASS |
| S-AKI | /disease-center/saki | native | - | /api/saki/overview | patient, score | researcher | PASS |
| Research Workbench | /research-workbench | native | postResearchTable1 | /api/research/analytics/table1 | research_analytics_tasks | researcher | PASS |
| Clinical Trials | /clinical-trials | native | - | /api/clinical-trials/candidates | clinical_trials | researcher | PASS |
| MDT | /mdt | native | getAiMdtWorkspace | /api/ai/mdt-workspace/{id} | - | all | PASS |
| AI Ops | /ai-ops | native | getAiMonitorSummary | /api/ai/monitor/summary | ai_monitor_logs | admin | PASS |
| Runtime Config | /admin/runtime-config | native | getRuntimeConfig | /api/admin/runtime-config | runtime_configs | admin | PASS |
| Big Screen | /bigscreen | native | getPatients | /api/patients | patient | all | PASS |
| Mobile | /m | native | getMobileHomeLite | /api/mobile/home-lite | patient | all | PASS |

## Notes

- **renderMode: native** = Vue component loaded directly in router
- **renderMode: embed** = Loaded in iframe via EmbedLayout
- **BLOCKED** = Feature flag disabled by default (ai-causal-inference, ai-what-if, ai-decision-assistants)
- All patient endpoints require valid JWT token
- Admin endpoints require admin role
- Research endpoints require researcher role
- Patient data isolation enforced via department/ward matching
