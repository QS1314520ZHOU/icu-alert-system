# ICU Alert System - 全系统模块清单

**生成时间**: 2026-08-30
**RUN_ID**: 8b4eeab1-6b78-47f8-a36c-e8f788402923

## 统计摘要

| 指标 | 数量 |
|------|------|
| 模块总数 | 42 |
| 后端API端点 | 346 |
| 前端路由 | 78 |
| API文件 | 12 |
| Vue视图组件 | 80+ |
| 嵌入模块(embed) | 9 |
| 移动端视图 | 8 |

## 模块分组

### A. 系统与认证 (1)
| 模块 | 路由 | 后端端点 | 状态 |
|------|------|----------|------|
| 登录与身份认证 | /, /403 | /api/auth/* (5) | pending |

### B. 角色首页 (4)
| 模块 | 路由 | 后端端点 | 角色限制 | 状态 |
|------|------|----------|----------|------|
| 医生首页 | /doctor-home | /api/home/doctor | doctor | pending |
| 护士首页 | /nurse-home | /api/home/nurse/* (6) | nurse | pending |
| 护士长首页 | /head-nurse-home | /api/home/head-nurse/* (2) | head_nurse | pending |
| 主任首页 | /director-home | /api/home/director | director | pending |

### C. 患者总览与工作流 (3)
| 模块 | 路由 | 后端端点 | 状态 |
|------|------|----------|------|
| 患者总览 | /patients | /api/patients/* (4) | pending |
| 临床工作台 | /clinical-workflow | /api/clinical-workflow/* (5) | pending |
| 智能交接班 | /handover/* (7) | /api/handover/* (10) | pending |

### D. 患者详情 (7)
| 模块 | 路由 | 后端端点 | 状态 |
|------|------|----------|------|
| 病情总览 | /patient/:id/overview | /api/patients/{id}/* (8) | pending |
| 实时监测 | /patient/:id/monitoring | /api/patients/{id}/vitals/*, /api/waveforms/* (5) | pending |
| 治疗与护理 | /patient/:id/treatment | /api/patients/{id}/drugs, /api/treatment/* (3) | pending |
| 临床预警 | /patient/:id/alerts | /api/patients/{id}/alerts, /api/alerts/* (4) | pending |
| AI文书 | /patient/:id/documents | /api/clinical-documents/* (6) | pending |
| 随访管理 | /patient/:id/followup | /api/followup_*/* (11) | pending |
| AI分析 | /patient/:id/intelligence | (入口页) | pending |

### E. AI嵌入模块 (8)
| 模块 | 路由 | 后端端点 | Feature Flag | 状态 |
|------|------|----------|--------------|------|
| 风险预测 | /embed/patient/:id/risk-prediction | /api/ai/risk-forecast/{id} | ai-risk-prediction | pending |
| 综合风险 | /embed/patient/:id/integrated-risk | /api/ai/integrated-risk/{id} | ai-integrated-risk | pending |
| 相似病例 | /embed/patient/:id/similar-cases | /api/patients/{id}/similar-case-outcomes | ai-similar-cases | pending |
| 因果推断 | /embed/patient/:id/causal-inference | /api/ai/causal-analysis/{id} | ai-causal-inference | pending |
| What-if模拟 | /embed/patient/:id/what-if | /api/ai/what-if/{id} | ai-what-if | pending |
| 病程推演 | /embed/patient/:id/disease-trajectory | /api/ai/clinical-reasoning/{id} | ai-disease-trajectory | pending |
| 循证证据 | /embed/patient/:id/evidence | /api/patients/{id}/evidence | ai-evidence | pending |
| 专项决策 | /embed/patient/:id/decision-assistants | (无) | ai-decision-assistants | pending |

### F. 临床专项 (4)
| 模块 | 路由 | 后端端点 | 状态 |
|------|------|----------|------|
| 呼吸治疗 | /respiratory-dashboard | /api/respiratory/* (8) | pending |
| 营养支持 | /nutrition-support | /api/nutrition/* (6) | pending |
| MDT会诊 | /mdt | /api/ai/mdt-workspace/* (4) | pending |
| AI问诊 | /ai-consult | /api/ai/chat-consult | pending |

### G. 科研模块 (5)
| 模块 | 路由 | 后端端点 | 状态 |
|------|------|----------|------|
| 病种中心 | /disease-center/* (10) | /api/disease-center/* (28+) | pending |
| S-AKI科研中心 | /disease-center/saki/* (9) | /api/disease-center/saki/* (32) | pending |
| 科研工作台 | /research-workbench | /api/research/* (26) | pending |
| 科研导出 | /research-export | /api/research/export/* (4) | pending |
| 临床试验筛选 | /clinical-trials | /api/clinical-trials/* (11) | pending |
| 学术科研支撑 | /academic-research | /api/research/projects, topic-suggestions, omop/* | pending |

### H. 管理模块 (5)
| 模块 | 路由 | 后端端点 | 状态 |
|------|------|----------|------|
| AI运营中心 | /ai-ops | /api/ai/monitor/summary, /api/ai/feedback/summary | pending |
| 配置中心 | /admin/runtime-config | /api/admin/runtime-config/* (10) | pending |
| 规则健康 | /admin/scanner-health | /api/admin/scanner-health/* (4) | pending |
| 语音纠错Review | /admin/voice-correction-review | /api/admin/voice-correction-candidates/* (3) | pending |
| 知识库 | (API only) | /api/knowledge/* (5) | pending |

### I. 显示与移动端 (3)
| 模块 | 路由 | 后端端点 | 状态 |
|------|------|----------|------|
| 护士站大屏 | /bigscreen | (无专用) | pending |
| 床旁大屏 | /bedside/:id | (无专用) | pending |
| 移动工作台 | /m/* (8) | /api/mobile/* (15) | pending |

### J. 系统监控 (1)
| 模块 | 路由 | 后端端点 | 状态 |
|------|------|----------|------|
| 系统监控 | (API only) | /monitoring/* (3) | pending |

## Feature Flags 状态

| Flag | 默认启用 | 允许角色 |
|------|----------|----------|
| ai-risk-prediction | ✅ | doctor, nurse, head_nurse, director |
| ai-integrated-risk | ✅ | doctor, nurse, head_nurse, director |
| ai-similar-cases | ✅ | doctor, director, researcher |
| ai-causal-inference | ❌ | doctor, director, researcher |
| ai-what-if | ❌ | doctor, director |
| ai-disease-trajectory | ✅ | doctor, nurse, director |
| ai-evidence | ✅ | doctor, nurse, head_nurse, director |
| ai-decision-assistants | ❌ | doctor, director |
| ai-documents | ✅ | doctor, nurse, head_nurse |
| ai-followup | ✅ | doctor, nurse, head_nurse |
