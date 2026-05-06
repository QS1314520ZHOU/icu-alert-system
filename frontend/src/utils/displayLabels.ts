const SCENARIO_GROUP_LABELS: Record<string, string> = {
  respiratory_failure: '呼吸衰竭',
  postoperative_general: '术后综合管理',
  post_liver_transplant: '肝移植术后',
  post_cardiac_surgery: '心外术后',
  drug_interactions: '药物相互作用',
  device_complications: '装置并发症',
  nutrition_endocrine: '营养与内分泌',
  infection_sepsis: '感染与脓毒症',
  renal_metabolic: '肾脏与代谢',
  rare_critical: '罕见危重症',
  post_neurosurgery: '神经外科术后',
  hemodynamic_instability: '血流动力学不稳定',
  hematology_transfusion: '血液与输血',
  neuro_critical: '神经重症',
}

const ALERT_TYPE_LABELS: Record<string, string> = {
  ards: 'ARDS',
  aki: 'AKI',
  qsofa: 'qSOFA',
  sofa: 'SOFA',
  septic_shock: '脓毒性休克',
  icp: '颅内压升高',
  cpp: '脑灌注压不足',
  gi_bleeding: '消化道出血',
  weaning: '撤机筛查',
  hit: 'HIT 风险',
  nephrotoxicity: '肾毒性风险',
  sedation: '过度镇静',
  qt_risk: 'QT 风险',
  af_afl_new_onset: '新发房颤/房扑',
  brady_hypotension: '心动过缓合并低压',
  qtc_prolonged: 'QTc 明显延长',
  opioid_high_dose_resp_risk: '阿片高剂量风险',
  opioid_respiratory_depression: '阿片呼吸抑制',
  opioid_withdrawal_risk: '阿片戒断风险',
  nurse_reminder: '护理提醒',
  lab_threshold: '检验阈值',
  threshold: '阈值提醒',
  trend_analysis: '趋势分析',
  ai_risk: 'AI 风险',
  fluid_balance: '液体平衡',
  delirium_risk: '谵妄风险',
  sedation_delirium_conversion: '镇静转谵妄',
  glucose_variability: '血糖波动',
  hypoglycemia: '低血糖',
  glucose_drop_fast: '血糖快速下降',
  glucose_recheck_reminder: '血糖复查提醒',
  hyperglycemia_no_insulin: '高血糖未启胰岛素',
  abx_timeout: '抗生素 time-out',
  abx_stop_recommendation: 'PCT 停药评估',
  abx_tdm_reminder: '抗生素 TDM 提醒',
  abx_duration_exceeded: '抗生素疗程超限',
  vte_prophylaxis_omission: 'VTE 预防遗漏',
  vte_bleeding_linkage: 'VTE 出血风险联动',
  vte_immobility_no_prophylaxis: '卧床无 VTE 预防',
  nutrition_start_delay: '营养启动延迟',
  nutrition_monitor: '营养监测',
  nutrition_calorie_not_reached: '热卡未达标',
  nutrition_feeding_intolerance: '喂养不耐受',
  nutrition_refeeding_risk: '再喂养风险',
  multi_organ_deterioration_trend: '多器官恶化趋势',
  organ_deterioration_trend: '器官恶化趋势',
  cvc_review: '中心静脉导管评估',
  foley_review: '导尿管评估',
  ett_extubation_delay: '拔管延迟',
  liberation_bundle: '撤机与镇静唤醒评估',
  liberation_bundle_overdue: '撤机与镇静唤醒逾期',
  fluid_responsiveness: '容量反应性',
  crrt_filter_clotting: 'CRRT 滤器凝堵',
  crrt_citrate_ica: '枸橼酸 iCa',
  crrt_heparin_act: '肝素 ACT',
  crrt_dose_low: 'CRRT 剂量不足',
  renal_dose_adjustment: '肾功能剂量调整',
  driving_pressure: '驱动压',
  pplat_high: '平台压升高',
  lung_protective_ventilation: '肺保护通气',
  mechanical_power: '机械功率',
  steroid_taper_after_vaso: '激素减停',
  steroid_long_term_taper: '长程激素减停',
  steroid_hyperglycemia: '激素相关高血糖',
  ecash_rass_off_target: 'RASS 未达目标',
  ecash_bundle: '镇痛镇静谵妄评估',
  ecash_sat_due: '自主唤醒试验到期',
  ecash_pain_overdue: '疼痛评估逾期',
  ecash_pain_uncontrolled: '疼痛控制不佳',
  ecash_benzo_in_use: '苯二氮卓使用中',
  ecash_sat_stress_reaction: '自主唤醒试验应激反应',
  icu_aw_risk: 'ICU 获得性衰弱高风险',
  early_mobility_recommendation: '早期活动建议',
  pe_suspected: '肺栓塞疑似',
  pe_wells_high: 'Wells 高风险',
  extubation_failure_risk: '拔管失败风险',
  post_extubation_failure_risk: '拔管后失败风险',
  elevated_icp_risk: '颅压升高风险',
  vent_driving_pressure: '呼吸机驱动压',
  delirium_risk_critical: '谵妄风险危急',
  emergency_admission: '急诊入院',
  hydrocephalus_acute: '急性脑积水',
  hypertensive_emergency: '高血压急症',
  sepsis_sofa: '脓毒症 SOFA 风险',
  sepsis_qsofa: '脓毒症 qSOFA 风险',
  sepsis_bundle_overdue_3h: '脓毒症救治清单超时',
  hai_vap_bundle_missing: 'VAP 预防清单缺项',
  vap_bundle_missing: 'VAP 预防清单缺项',
  hai_cvc_review: '中心静脉导管感染风险评估',
  hai_cauti_risk: '导尿管感染风险',
  integrated_risk_reasoning: '综合风险推理',
  scanner_nurse_reminders: '护理提醒',
  scanner_nursing_workload: '护理工作负荷',
  scanner_nutrition_monitor: '营养监测',
  scanner_ventilator_weaning: '撤机评估',
  scanner_vanco_tdm_closed_loop: '万古霉素 TDM 闭环',
  crrt_monitor: 'CRRT 监测',
  hai_bundle_monitor: '院感防控清单监测',
  circadian_protector: '昼夜节律保护',
  clinical_reasoning_agent: '临床推理助手',
  ai_handoff: '智能交班',
  pulse: '主动提醒',
  proactive: '主动干预',
  metabolic: '代谢评估',
}

export function formatAlertTypeLabel(value: any) {
  const raw = String(value || '').trim()
  const key = raw.toLowerCase().replace(/[\s-]+/g, '_')
  if (!key) return '未命名规则'
  return ALERT_TYPE_LABELS[key] || raw
    .replace(/_/g, ' ')
    .replace(/\bSOFA\b/i, 'SOFA')
    .replace(/\bQSOFA\b/i, 'qSOFA')
    .replace(/\bVAP\b/i, 'VAP')
    .replace(/\bHAI\b/i, '院感')
    .replace(/\bBUNDLE\b/i, '清单')
    .replace(/\bNUTRITION\b/i, '营养')
    .replace(/\bLIBERATION\b/i, '撤机')
    .replace(/\bOVERDUE\b/i, '逾期')
    .replace(/\bSTART\b/i, '启动')
    .replace(/\bDELAY\b/i, '延迟')
    .replace(/\bSEPSIS\b/i, '脓毒症')
}

const COMPOSITE_GROUP_LABELS: Record<string, string> = {
  sepsis_group: '脓毒症主题',
  bleeding_group: '出血主题',
  respiratory_group: '呼吸主题',
}

const COMPOSITE_CHAIN_LABELS: Record<string, string> = {
  shock_chain: '休克链',
  respiratory_failure_chain: '呼衰链',
  sepsis_progression_chain: '脓毒症进展链',
  bleeding_chain: '失血链',
  multi_organ_progression: '多器官进展',
}

export function formatScenarioGroupLabel(value: any) {
  const key = String(value || '').trim().toLowerCase().replace(/[\s-]+/g, '_')
  if (!key) return '未分组'
  return SCENARIO_GROUP_LABELS[key] || key.replace(/_/g, ' ')
}

export function formatCompositeGroupLabel(value: any) {
  const key = String(value || '').trim().toLowerCase().replace(/[\s-]+/g, '_')
  if (!key) return '未分组'
  return COMPOSITE_GROUP_LABELS[key] || key.replace(/_/g, ' ')
}

export function formatCompositeChainLabel(value: any) {
  const key = String(value || '').trim().toLowerCase().replace(/[\s-]+/g, '_')
  if (!key) return '未定义链路'
  return COMPOSITE_CHAIN_LABELS[key] || key.replace(/_/g, ' ')
}

const EXPLANATION_FIELD_LABELS: Record<string, string> = {
  recent_high_alerts: '近期高危告警已解除',
  recent_high_alerts_count: '近期高危告警次数',
  sofa_trend_down: 'SOFA 趋势下降',
  sofa_trend: 'SOFA 趋势',
  sofa_delta: 'SOFA 变化值',
  sofa_lookback_hours: 'SOFA 回看时长',
  off_vasopressor: '已停用升压药',
  on_vasopressor: '正在使用升压药',
  oxygenation_ok: '氧合达标',
  fio2: 'FiO2',
  peep: 'PEEP',
  gcs_ok: 'GCS 达标',
  gcs: 'GCS',
  urine_ok: '尿量达标',
  urine_6h_ml_kg_h: '近 6 小时尿量',
  transfer_signal: '转运信号',
  candidate: '可转运',
  type: '信号类型',
  time: '时间',
  evidence: '依据',
  recent_count: '最近窗口次数',
  previous_count: '前一窗口次数',
  route_targets: '路由对象',
  nurse: '护士',
  doctor: '医生',
  hdu: 'HDU',
}

export function formatExplanationFieldLabel(value: any) {
  const key = String(value || '').trim()
  if (!key) return ''
  return EXPLANATION_FIELD_LABELS[key] || key.replace(/_/g, ' ')
}

