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
  ards_oxygenation_screen: 'ARDS 氧合筛查',
  ventilator_lung_injury_risk: '呼吸机肺损伤风险',
  aki: 'AKI',
  qsofa: 'qSOFA',
  sofa: 'SOFA',
  septic_shock: '可能脓毒性休克表型',
  shock_hypoperfusion_screen: '休克/低灌注筛查',
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
  trajectory_drift: '病情轨迹漂移',
  ventilator_asynchrony: '人机不同步',
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
  abx_timeout: '抗菌药复核超时',
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
  forecast_threshold_breach: '预测达到预警阈值',
  pics_risk: 'ICU后综合征风险',
}

export function formatAlertTypeLabel(value: any) {
  const raw = String(value || '').trim()
  const key = raw.toLowerCase().replace(/[\s-]+/g, '_')
  if (!key) return '未命名规则'
  if (ALERT_TYPE_LABELS[key]) return ALERT_TYPE_LABELS[key]
  if (/[_-]/.test(key)) {
    const translated = key.split('_')
      .map((part) => ALERT_TYPE_LABELS[part] || CLINICAL_TERM_LABELS[part] || '')
      .filter(Boolean)
    if (translated.length) return Array.from(new Set(translated)).join('')
    return '未命名规则'
  }
  return raw
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

const SEVERITY_LABELS: Record<string, string> = {
  critical: '危急',
  high: '高危',
  warning: '预警',
  warn: '预警',
  medium: '中危',
  info: '关注',
  low: '低危',
  normal: '正常',
  none: '正常',
  ok: '正常',
  failure: '衰竭',
  impaired: '受损',
  blocked: '阻断',
  red: '红色',
  yellow: '黄色',
  green: '绿色',
}

const RISK_LABELS: Record<string, string> = {
  critical: '危急风险',
  high: '高风险',
  warning: '预警风险',
  medium: '中风险',
  low: '低风险',
  normal: '低风险',
  none: '低风险',
  unknown: '未分层',
}

const STATUS_LABELS: Record<string, string> = {
  pending: '待处理',
  pending_review: '待审核',
  open: '待处理',
  in_progress: '处理中',
  active: '执行中',
  monitoring: '监测中',
  completed: '已完成',
  closed: '已关闭',
  cancelled: '已取消',
  dismissed: '不采纳',
  approved: '已批准',
  rejected: '已拒绝',
  accepted: '已接收',
  scheduled: '已排期',
  resolved: '已处理',
  false_positive: '不是问题',
  todo: '待完成',
  done: '已完成',
  draft: '草稿',
  confirmed: '已确认',
  failed: '失败',
  success: '成功',
  ok: '正常',
  normal: '正常',
  blocked: '阻断',
  impaired: '受损',
  failure: '衰竭',
}

const CLINICAL_TERM_LABELS: Record<string, string> = {
  integrated_risk: '综合风险',
  integrated_risk_reasoning: '综合风险推理',
  risk_level: '风险等级',
  risk_score: '风险评分',
  score: '评分',
  factor: '因素',
  factors: '因素',
  mechanical_ventilation: '机械通气',
  metabolic_acidosis: '代谢性酸中毒',
  mechanical_ventilation_ge_3d: '机械通气超过3天',
  mechanical_ventilation_ge_7d: '机械通气超过7天',
  sepsis_active: '存在脓毒症相关预警',
  ventilation_days: '机械通气天数',
  forecast_timeout: '预测计算超时',
  forecast_unavailable: '预测暂不可用',
  forecast_threshold_breach: '预测达到预警阈值',
  trajectory_forecast: '轨迹预测',
  temporal_risk_forecast: '时序风险预测',
  model_not_loaded: '模型未就绪',
  model_not_ready: '模型未就绪',
  model_inference_error: '模型推理失败',
  insufficient_history: '历史数据不足',
  nurse_reminder: '护理提醒',
  nutrition_start_delay: '营养启动延迟',
  delirium_risk: '谵妄风险',
  pe_wells_high: 'Wells 高风险',
  weaning: '撤机筛查',
  pics_risk: 'ICU后综合征风险',
  neuro: '神经',
  resp: '呼吸',
  cv: '循环',
  heme: '血液',
  endo: '内分泌',
  hfnc: '高流量氧疗',
  hf: '高流量氧疗',
  niv: '无创通气',
  vap_bundle_missing: 'VAP 预防清单缺项',
  bedside: '床旁记录',
  bedside_text: '床旁记录',
  devicecap: '监护设备',
  tubeexe: '管路执行记录',
  severity: '严重程度',
  status: '状态',
  evidence: '依据',
  suggestions: '建议',
  recommendation: '建议',
  reasoning: '推理依据',
  review_time: '复评时间',
  worsening_indicators: '恶化趋势指标',
  fibrinolysis_state: '纤溶状态',
  fibrinolysis: '纤溶',
  modi: '多器官恶化指数',
  multi_organ_deterioration_index: '多器官恶化指数',
  gcs: '格拉斯哥昏迷评分',
  glasgow_coma_scale: '格拉斯哥昏迷评分',
  rass: '镇静躁动评分',
  cam_icu: '谵妄评估',
  sofa: '序贯器官衰竭评分',
  qsofa: '快速序贯器官衰竭评分',
  trajectory_drift: '病情轨迹漂移',
  ventilator_asynchrony: '人机不同步',
  apache: '急性生理与慢性健康评分',
  ards: '急性呼吸窘迫综合征',
  ards_oxygenation_screen: 'ARDS 氧合分级筛查',
  ventilator_lung_injury_risk: '肺保护通气偏离风险',
  aki: '急性肾损伤',
  crrt: '连续肾脏替代治疗',
  vte: '静脉血栓栓塞',
  vap: '呼吸机相关肺炎',
  hai: '院内感染',
  hit: '肝素诱导性血小板减少',
  map: '平均动脉压',
  sbp: '收缩压',
  dbp: '舒张压',
  bp: '血压',
  hr: '心率',
  rr: '呼吸频率',
  spo2: '血氧饱和度',
  fio2: '吸入氧浓度',
  peep: '呼气末正压',
  pf_ratio: '氧合指数',
  p_f_ratio: '氧合指数',
  pao2: '动脉氧分压',
  paco2: '动脉二氧化碳分压',
  temp: '体温',
  temperature: '体温',
  lactate: '乳酸',
  lac: '乳酸',
  creatinine: '肌酐',
  cr: '肌酐',
  bun: '尿素氮',
  wbc: '白细胞',
  rbc: '红细胞',
  hb: '血红蛋白',
  hgb: '血红蛋白',
  plt: '血小板',
  pct: '降钙素原',
  crp: 'C 反应蛋白',
  il6: '白介素 6',
  inr: '国际标准化比值',
  aptt: '活化部分凝血活酶时间',
  pt: '凝血酶原时间',
  ddimer: 'D-二聚体',
  d_dimer: 'D-二聚体',
  fibrinogen: '纤维蛋白原',
  glucose: '血糖',
  glu: '血糖',
  sodium: '钠',
  potassium: '钾',
  chloride: '氯',
  calcium: '钙',
  magnesium: '镁',
  bilirubin: '胆红素',
  albumin: '白蛋白',
  alt: '谷丙转氨酶',
  ast: '谷草转氨酶',
  ph: '酸碱度',
  urine: '尿量',
  urine_output: '尿量',
  vasopressor: '升压药',
  ventilator: '呼吸机',
  ventilation: '通气',
  mechanical: '机械',
  acidosis: '酸中毒',
  oxygenation: '氧合',
  sedation: '镇静',
  delirium: '谵妄',
  sepsis: '脓毒症',
  shock: '休克',
  bleeding: '出血',
  infection: '感染',
  nutrition: '营养',
  renal: '肾脏',
  respiratory: '呼吸',
  hemodynamic: '血流动力学',
  neurological: '神经系统',
  metabolic: '代谢',
  coagulation: '凝血',
  cardiac: '心脏',
  liver: '肝脏',
  kidney: '肾脏',
  lung: '肺部',
  high_risk: '高风险',
  medium_risk: '中风险',
  low_risk: '低风险',
  critical_risk: '危急风险',
}

function normalizeLabelKey(value: any) {
  return String(value || '').trim().toLowerCase().replace(/[\s-]+/g, '_')
}

export function formatSeverityLabel(value: any, fallback = '关注') {
  const key = normalizeLabelKey(value)
  if (!key) return fallback
  return SEVERITY_LABELS[key] || fallback
}

// ═══════════════════════════════════════════════════════════════════════════
// 告警领域 (alert_domain) 和优先级 (priority) 标签
// ═══════════════════════════════════════════════════════════════════════════

const DOMAIN_LABELS: Record<string, string> = {
  physiologic_alarm: '生理危急',
  clinical_risk: '临床风险',
  workflow_reminder: '流程提醒',
  quality_gap: '质控缺项',
  data_quality: '数据质量',
  ai_advisory: 'AI 建议',
  unknown: '未分类',
}

const DOMAIN_DISPLAY_TONES: Record<string, string> = {
  physiologic_alarm: 'red',
  clinical_risk: 'orange',
  workflow_reminder: 'amber',
  quality_gap: 'yellow',
  data_quality: 'slate',
  ai_advisory: 'blue',
  unknown: 'slate',
}

const DOMAIN_CSS_CLASSES: Record<string, string> = {
  red: 'domain-physiologic',
  orange: 'domain-clinical',
  amber: 'domain-workflow',
  yellow: 'domain-quality',
  slate: 'domain-data',
  blue: 'domain-ai',
}

const PRIORITY_LABELS: Record<string, string> = {
  p0: '立即响应',
  p1: '尽快处理',
  p2: '本班处理',
  p3: '例行',
}

const PRIORITY_SORT_ORDER: Record<string, number> = {
  p0: 0,
  p1: 1,
  p2: 2,
  p3: 3,
}

export function formatDomainLabel(value: any, fallback = '未分类') {
  const key = normalizeLabelKey(value)
  if (!key) return fallback
  return DOMAIN_LABELS[key] || fallback
}

export function formatPriorityLabel(value: any, fallback = '—') {
  const key = normalizeLabelKey(value)
  if (!key) return fallback
  return PRIORITY_LABELS[key] || fallback
}

export function getDomainDisplayTone(domain: string | null | undefined): string {
  const key = normalizeLabelKey(domain)
  return DOMAIN_DISPLAY_TONES[key] || 'slate'
}

export function getDomainCssClass(tone: string): string {
  return DOMAIN_CSS_CLASSES[tone] || 'domain-unknown'
}

export function getPrioritySortOrder(priority: string | null | undefined): number {
  const key = normalizeLabelKey(priority)
  return PRIORITY_SORT_ORDER[key] ?? 2  // default to p2
}

/**
 * 前端显示色调映射（优先使用 alert_domain → display_tone → severity 降级）
 */
export function getAlertDisplayTone(alert: any): string {
  // 1) alert_domain 优先
  if (alert?.alert_domain) {
    return getDomainDisplayTone(alert.alert_domain)
  }
  // 2) display_tone 字段
  if (alert?.display_tone) {
    return String(alert.display_tone).toLowerCase()
  }
  // 3) 旧 severity 降级
  const sev = String(alert?.severity || '').toLowerCase()
  if (sev === 'critical') return 'red'
  if (sev === 'high') return 'orange'
  if (sev === 'warning') return 'amber'
  return 'slate'
}

/**
 * 是否应该触发强提醒（弹窗/声音）
 * 仅 physiologic_alarm + p0 触发
 */
export function shouldTriggerStrongNotification(alert: any): boolean {
  const domain = String(alert?.alert_domain || '').toLowerCase()
  const priority = String(alert?.priority || '').toLowerCase()
  return domain === 'physiologic_alarm' && priority === 'p0'
}

/**
 * 是否应该触发语音播报
 * 仅 physiologic_alarm + p0
 */
export function shouldTriggerSpeech(alert: any): boolean {
  return shouldTriggerStrongNotification(alert)
}

/**
 * 大屏显示过滤：默认仅显示 p0/p1
 */
export function isBigScreenVisible(alert: any): boolean {
  const priority = String(alert?.priority || '').toLowerCase()
  return priority === 'p0' || priority === 'p1'
}

/**
 * 护理任务面板显示过滤：显示 workflow_reminder 和 quality_gap
 */
export function isNursingTaskVisible(alert: any): boolean {
  const domain = String(alert?.alert_domain || '').toLowerCase()
  return domain === 'workflow_reminder' || domain === 'quality_gap'
}

export function formatRiskLevelLabel(value: any, fallback = '未分层') {
  const key = normalizeLabelKey(value)
  if (!key) return fallback
  return RISK_LABELS[key] || formatSeverityLabel(key, fallback)
}

export function formatStatusLabel(value: any, fallback = '未知') {
  const key = normalizeLabelKey(value)
  if (!key) return fallback
  return STATUS_LABELS[key] || SEVERITY_LABELS[key] || String(value || fallback).replace(/_/g, ' ')
}

export function formatClinicalTermLabel(value: any, fallback = '临床指标') {
  const raw = String(value ?? '').trim()
  const key = normalizeLabelKey(raw)
  if (!key) return fallback
  if (CLINICAL_TERM_LABELS[key]) return CLINICAL_TERM_LABELS[key]
  if (ALERT_TYPE_LABELS[key]) return ALERT_TYPE_LABELS[key]
  if (STATUS_LABELS[key]) return STATUS_LABELS[key]
  if (RISK_LABELS[key]) return RISK_LABELS[key]
  if (SEVERITY_LABELS[key]) return SEVERITY_LABELS[key]
  if (/^[a-z][a-z0-9_-]*$/i.test(raw) && /[_-]/.test(raw)) {
    const translated = key.split('_').map((part) => CLINICAL_TERM_LABELS[part] || STATUS_LABELS[part] || RISK_LABELS[part] || SEVERITY_LABELS[part] || '').filter(Boolean)
    if (translated.length) return Array.from(new Set(translated)).join('')
    return fallback
  }
  if (/^[A-Z]{2,}$/i.test(raw)) return raw
  if (/^[a-z]{2,}$/i.test(raw)) return fallback
  return raw
}

export function formatClinicalText(value: any, fallback = '暂无') {
  const raw = String(value ?? '').trim()
  if (!raw) return fallback
  const protectedTerms = new Map<string, string>()
  let text = raw.replace(/\b(?:I-PASS|ISBAR|AI)\b/g, (match) => {
    const token = `__KEEP_${protectedTerms.size}__`
    protectedTerms.set(token, match)
    return token
  })
  text = text
    .replace(/timeout of \d+ms exceeded/gi, '请求超时，请稍后重试')
    .replace(/\bECONNABORTED\b/gi, '请求超时')
    .replace(/model (?:not ready|not loaded)/gi, '模型未就绪')
    .replace(/model unavailable/gi, '模型暂不可用')
    .replace(/service unavailable/gi, '服务暂不可用')
    .replace(/\btime-out\b/gi, '复核超时')
    .replace(/\bNeuro\s+(神经)/gi, '$1')
    .replace(/\bResp\s+(呼吸)/gi, '$1')
    .replace(/\bCV\s+(循环)/gi, '$1')
    .replace(/\bRenal\/Fluid\s+(肾脏)/gi, '$1')
    .replace(/\bGI\/Nutrition\s+(消化)/gi, '$1')
    .replace(/\bID\s+(感染)/gi, '$1')
    .replace(/\bHeme\s+(?:凝血|血液)/gi, '血液')
    .replace(/\bEndo\s+(内分泌)/gi, '$1')
    .replace(/\bLines\/Devices\s+(管路)/gi, '$1')
    .replace(/\bGoals\s+(今日目标)/gi, '$1')
  text = text.replace(
    /\b[a-zA-Z][a-zA-Z0-9]*(?:[_-][a-zA-Z0-9]+)+\b|\b(?:critical|high|warning|warn|medium|low|normal|pending|active|resolved|open|closed|completed|failed|success|impaired|failure|blocked|modi|gcs|sofa|qsofa|rass|plt|map|spo2|sbp|dbp|hr|rr|temp|lac|cr|wbc|pct|inr|neuro|resp|cv|heme|endo|hfnc|hf|niv)\b/gi,
    (match) => formatClinicalTermLabel(match, match),
  )
  protectedTerms.forEach((value, token) => {
    text = text.replace(token, value)
  })
  return text
}

