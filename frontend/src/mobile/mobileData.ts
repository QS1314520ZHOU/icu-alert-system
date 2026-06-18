function textFromValue(value: any): string {
  if (value == null) return ''
  if (Array.isArray(value)) return value.map(textFromValue).filter(Boolean).join('、')
  if (typeof value === 'object') {
    for (const key of ['text', 'summary', 'diagnosis', 'name', 'title', 'content', 'description', 'value', 'label']) {
      const text = textFromValue(value?.[key])
      if (text) return text
    }
    return ''
  }
  return String(value).trim()
}

export function firstText(row: any, keys: string[], fallback = '') {
  for (const key of keys) {
    const value = row?.[key]
    const text = textFromValue(value)
    if (text) return text
  }
  return fallback
}

export function patientDiagnosisOf(row: any, fallback = '暂无诊断摘要') {
  return firstText(
    row,
    [
      'clinicalDiagnosis',
      'admissionDiagnosis',
      'diagnosis',
      'diagnose',
      'hisDiagnosis',
      'hisDiagnose',
      'mainDiagnosis',
      'primaryDiagnosis',
      'diagnosisName',
      'diagnosisDesc',
      'allDiagnosis',
      'diagnosisHistory',
      'diagnosisHistoryList',
      'curIcuDiagnosisHistory',
      'dischargedDiagnosis',
      'chiefComplaint',
      'presentIllness',
      'clinical_summary',
      'summary',
      'remark',
    ],
    fallback,
  )
}

export function firstNumber(row: any, keys: string[], fallback = 0) {
  for (const key of keys) {
    const value = Number(row?.[key])
    if (Number.isFinite(value)) return value
  }
  return fallback
}

export function patientIdOf(row: any) {
  return firstText(row, ['patient_id', 'patientId', '_id', 'id', 'hisPid'])
}

export function patientRouteIdOf(row: any) {
  return firstText(row, ['_id', 'id', 'patient_id', 'patientId', 'hisPid'])
}

export function patientNameOf(row: any) {
  return firstText(row, ['name', 'patient_name', 'patientName', 'hisName', '姓名'], '患者')
}

export function bedOf(row: any) {
  return firstText(row, ['hisBed', 'bed_no', 'bedNo', 'bed', 'bedLabel', '床号'], '--')
}

export function alertIdOf(row: any) {
  return firstText(row, ['alert_id', 'alertId', '_id', 'id'])
}

const PHRASE_LABELS: Record<string, string> = {
  icuaw: 'ICU-AW',
  icu_aw: 'ICU-AW',
  icuawscore: 'ICU-AW评分',
  icu_aw_score: 'ICU-AW评分',
  icustayhours: 'ICU住院时长',
  icu_stay_hours: 'ICU住院时长',
  bundlelights: 'Bundle合规待补全',
  bundle_lights: 'Bundle合规待补全',
  etco2: '呼气末二氧化碳',
  end_tidal_co2: '呼气末二氧化碳',
  spo2: '血氧饱和度',
  pao2: '动脉氧分压',
  fio2: '吸入氧浓度',
  map: '平均动脉压',
  hr: '心率',
  rr: '呼吸频率',
  sbp: '收缩压',
  dbp: '舒张压',
  temp: '体温',
  temperature: '体温',
  lactate: '乳酸',
  creatinine: '肌酐',
  bilirubin: '胆红素',
  platelet: '血小板',
  potassium: '血钾',
  sodium: '血钠',
  glucose: '血糖',
  wbc: '白细胞',
  pct: '降钙素原',
  crp: 'C反应蛋白',
  apache: 'APACHE',
  apacheii: 'APACHE II',
  apache_ii: 'APACHE II',
  sofa: 'SOFA评分',
  gcs: 'GCS评分',
}

const LABELS: Record<string, string> = {
  critical: '危急',
  urgent: '危急',
  red: '危急',
  high: '高危',
  warning: '预警',
  warn: '预警',
  orange: '高危',
  yellow: '高危',
  medium: '中危',
  moderate: '中危',
  low: '低危',
  watch: '关注',
  stable: '平稳',
  normal: '正常',
  active: '进行中',
  pending: '待处理',
  open: '待处理',
  assigned: '已分派',
  completed: '已完成',
  closed: '已关闭',
  acknowledged: '已确认',
  false_positive: '误报',
  handoff_doctor: '转医生',
  handoff_nurse: '转护士',
  sbar_handoff: 'SBAR移交',
  review_later: '稍后复评',
  handled: '已处理',
  sepsis: '脓毒症风险',
  septic_shock: '感染性休克风险',
  shock: '休克风险',
  hypotension: '低血压',
  hypertension: '高血压',
  tachycardia: '心动过速',
  bradycardia: '心动过缓',
  hypoxemia: '低氧血症',
  respiratory_failure: '呼吸衰竭风险',
  respiratory: '呼吸风险',
  ards: 'ARDS风险',
  ventilator_asynchrony: '人机不同步',
  ventilator_weaning: '脱机评估',
  extubation_failure: '拔管失败风险',
  aki: '急性肾损伤风险',
  renal_failure: '肾功能异常',
  renal: '肾功能风险',
  urine: '尿量风险',
  oliguria: '少尿',
  hyperlactatemia: '乳酸升高',
  fever: '发热',
  hypothermia: '低体温',
  infection: '感染风险',
  vte: 'VTE风险',
  pe: '肺栓塞风险',
  bleeding: '出血风险',
  gi_bleeding: '消化道出血风险',
  delirium: '谵妄风险',
  pain: '疼痛风险',
  pressure_injury: '压力性损伤风险',
  malnutrition: '营养风险',
  nutrition: '营养支持风险',
  hyperglycemia: '高血糖',
  hypoglycemia: '低血糖',
  electrolyte: '电解质异常',
  anemia: '贫血',
  thrombocytopenia: '血小板减少',
  drug_safety: '用药安全',
  antimicrobial: '抗菌药物风险',
  vanco_tdm: '万古霉素TDM风险',
  beta_blocker: 'β受体阻滞剂建议',
  prone_position: '俯卧位风险',
  pics: 'PICS风险',
}

const TOKEN_LABELS: Record<string, string> = {
  ai: '辅助',
  tdm: 'TDM',
  sbt: 'SBT',
  sat: 'SAT',
  ards: 'ARDS',
  sofa: 'SOFA评分',
  vte: 'VTE',
  pe: '肺栓塞',
  aki: 'AKI',
  pics: 'PICS',
  icu: 'ICU',
  aw: '肌无力',
  score: '评分',
  stay: '住院',
  hours: '时长',
  bundle: 'Bundle',
  lights: '合规待补全',
  co2: '二氧化碳',
  risk: '风险',
  alert: '告警',
  warning: '预警',
  critical: '危急',
  high: '高危',
  low: '低危',
  sepsis: '脓毒症',
  shock: '休克',
  respiratory: '呼吸',
  ventilator: '呼吸机',
  weaning: '脱机',
  failure: '失败',
  infection: '感染',
  bleeding: '出血',
  drug: '药物',
  nutrition: '营养',
  delirium: '谵妄',
  pressure: '压力性',
  injury: '损伤',
}

function normalizeKey(value: any) {
  return String(value ?? '')
    .trim()
    .replace(/([a-z0-9])([A-Z])/g, '$1_$2')
    .toLowerCase()
    .replace(/[\s\-/.]+/g, '_')
    .replace(/^scanner_/, '')
    .replace(/^rule_/, '')
    .replace(/^param_/, '')
}

function splitKey(key: string) {
  const direct = key.split('_').filter(Boolean)
  if (direct.length > 1) return direct
  const compact = key.match(/[a-z]+|\d+/g)
  return compact?.length ? compact : [key]
}

function translateTokenText(raw: string) {
  let text = raw
  const replacements = Object.entries({ ...PHRASE_LABELS, ...LABELS }).sort((a, b) => b[0].length - a[0].length)
  for (const [key, label] of replacements) {
    text = text.replace(new RegExp(key, 'ig'), label)
  }
  return text
}

export function labelText(value: any, fallback = '') {
  const raw = String(value ?? '').trim()
  if (!raw || raw === '--') return fallback
  const key = normalizeKey(raw)
  if (LABELS[key]) return LABELS[key]
  if (PHRASE_LABELS[key]) return PHRASE_LABELS[key]
  if (/[\u4e00-\u9fa5]/.test(raw)) return translateTokenText(raw)
  const translated = translateTokenText(key)
  if (/[\u4e00-\u9fa5]/.test(translated)) return translated.replace(/_/g, '')
  const parts = splitKey(key)
  if (!parts.length) return raw
  return parts.map((part) => PHRASE_LABELS[part] || LABELS[part] || TOKEN_LABELS[part] || part.toUpperCase()).join('')
}

export function levelOf(row: any) {
  const direct = firstText(row, ['level', 'severity', 'risk_level', 'alert_level', 'alertLevel'])
  if (direct) return normalizeKey(direct)
  const nested = firstText(row?.latest_alert, ['level', 'severity', 'risk_level', 'alert_level', 'alertLevel'])
  return normalizeKey(nested || 'watch')
}

export function toneOf(row: any) {
  const level = levelOf(row)
  if (['critical', 'urgent', 'red', '危急'].includes(level)) return 'critical'
  if (['high', 'warning', 'warn', 'medium', 'moderate', 'orange', 'yellow', '高危', '预警', '中危'].includes(level)) return 'warning'
  if (['normal', 'stable', 'green', '平稳', '正常'].includes(level)) return 'stable'
  return 'watch'
}

export function levelLabel(row: any) {
  const tone = toneOf(row)
  if (tone === 'critical') return '危急'
  if (tone === 'warning') return '高危'
  if (tone === 'stable') return '平稳'
  return '关注'
}

export function alertTitleOf(row: any) {
  const text = firstText(row, ['title_cn', 'title', 'name', 'alert_name', 'scanner_name'])
  if (text) return labelText(text, '风险告警')
  return labelText(firstText(row, ['alert_type', 'rule_id', 'category', 'parameter']), '风险告警')
}

export function alertSummaryOf(row: any) {
  const text = firstText(row, ['message_cn', 'summary_cn', 'message', 'summary', 'description', 'explanation'])
  if (text) return labelText(text, text)
  const parameter = labelText(firstText(row, ['parameter', 'metric', 'field']))
  const value = firstText(row, ['value', 'current_value', 'score'])
  const condition = labelText(firstText(row, ['condition', 'operator']))
  return [parameter, condition, value].filter(Boolean).join(' ') || '暂无说明'
}

export function formatTime(value: any) {
  if (!value) return '--'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

export function genderLabel(value: any) {
  const raw = String(value ?? '').trim()
  const text = raw.toLowerCase()
  if (!text || text === '--') return '--'
  if (['m', 'male', 'man', '1', '男', '男性'].includes(text)) return '男'
  if (['f', 'female', 'woman', '2', '女', '女性'].includes(text)) return '女'
  if (raw.includes('男')) return '男'
  if (raw.includes('女')) return '女'
  return raw
}

export function ageLabel(value: any) {
  const raw = String(value ?? '').trim()
  if (!raw || raw === '--') return '--'
  const normalized = raw.replace(/岁/g, '').trim()
  return normalized || '--'
}

export function arrayFromResponse(data: any, keys: string[] = []) {
  if (Array.isArray(data)) return data
  for (const key of keys) {
    if (Array.isArray(data?.[key])) return data[key]
  }
  if (Array.isArray(data?.items)) return data.items
  if (Array.isArray(data?.rows)) return data.rows
  if (Array.isArray(data?.data)) return data.data
  return []
}
