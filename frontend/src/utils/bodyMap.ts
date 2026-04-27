export const BODY_MAP_ORGAN_ORDER = [
  'neurologic',
  'respiratory',
  'circulatory',
  'hepatic',
  'coagulation',
  'renal',
] as const

export type BodyMapOrganKey = typeof BODY_MAP_ORGAN_ORDER[number]
export type BodyMapSeverity = 'normal' | 'warning' | 'high' | 'critical'

export const BODY_MAP_ORGAN_LABELS: Record<BodyMapOrganKey, string> = {
  neurologic: '神经',
  respiratory: '呼吸',
  circulatory: '循环',
  hepatic: '肝脏',
  coagulation: '凝血',
  renal: '肾脏',
}

const ORGAN_KEY_ALIASES: Record<string, BodyMapOrganKey> = {
  neuro: 'neurologic',
  neurologic: 'neurologic',
  neurological: 'neurologic',
  respiratory: 'respiratory',
  pulmonary: 'respiratory',
  lung: 'respiratory',
  circulatory: 'circulatory',
  cardiovascular: 'circulatory',
  cardiac: 'circulatory',
  hemodynamic: 'circulatory',
  hepatic: 'hepatic',
  liver: 'hepatic',
  coagulation: 'coagulation',
  hematologic: 'coagulation',
  renal: 'renal',
  kidney: 'renal',
}

const SEVERITY_RANK: Record<BodyMapSeverity, number> = {
  normal: 0,
  warning: 1,
  high: 2,
  critical: 3,
}

export function normalizeBodyMapOrganKey(value: any): BodyMapOrganKey | '' {
  return ORGAN_KEY_ALIASES[String(value || '').trim().toLowerCase()] || ''
}

export function normalizeBodyMapSeverity(value: any): BodyMapSeverity {
  const key = String(value || '').trim().toLowerCase()
  if (key === 'critical' || key === 'failure' || key === 'red') return 'critical'
  if (key === 'high' || key === 'orange') return 'high'
  if (key === 'warning' || key === 'warn' || key === 'impaired' || key === 'yellow' || key === 'medium') return 'warning'
  return 'normal'
}

export function bodyMapSeverityRank(value: any) {
  return SEVERITY_RANK[normalizeBodyMapSeverity(value)]
}

export function bodyMapSeverityText(value: any) {
  const normalized = normalizeBodyMapSeverity(value)
  return ({
    normal: '正常',
    warning: '预警',
    high: '高危',
    critical: '危急',
  } as Record<BodyMapSeverity, string>)[normalized]
}

export function bodyMapSeverityColor(value: any) {
  const normalized = normalizeBodyMapSeverity(value)
  return ({
    normal: '#34d399',
    warning: '#fbbf24',
    high: '#fb923c',
    critical: '#f43f5e',
  } as Record<BodyMapSeverity, string>)[normalized]
}

export function bodyMapScoreToSeverity(value: any): BodyMapSeverity {
  const score = Number(value)
  if (!Number.isFinite(score) || score <= 0) return 'normal'
  if (score >= 3) return 'critical'
  if (score >= 2) return 'high'
  return 'warning'
}

export function bodyMapStatusToSeverity(value: any): BodyMapSeverity {
  const key = String(value || '').trim().toLowerCase()
  if (key === 'failure') return 'critical'
  if (key === 'impaired') return 'warning'
  return 'normal'
}

export function createEmptyOrganStateMap() {
  return Object.fromEntries(
    BODY_MAP_ORGAN_ORDER.map((key) => [key, 'normal'])
  ) as Record<BodyMapOrganKey, BodyMapSeverity>
}

export function mergeOrganStateMaps(
  ...maps: Array<Partial<Record<BodyMapOrganKey, BodyMapSeverity>> | null | undefined>
) {
  const merged = createEmptyOrganStateMap()
  for (const map of maps) {
    if (!map) continue
    for (const organ of BODY_MAP_ORGAN_ORDER) {
      const next = normalizeBodyMapSeverity(map[organ])
      if (bodyMapSeverityRank(next) > bodyMapSeverityRank(merged[organ])) {
        merged[organ] = next
      }
    }
  }
  return merged
}

export function buildOrganStateMapFromCompositeExtra(extra: any) {
  const rows = createEmptyOrganStateMap()
  const scores = extra?.organ_scores && typeof extra.organ_scores === 'object' ? extra.organ_scores : {}
  for (const [rawKey, rawValue] of Object.entries(scores)) {
    const key = normalizeBodyMapOrganKey(rawKey)
    if (!key) continue
    rows[key] = bodyMapScoreToSeverity(rawValue)
  }
  const involved = Array.isArray(extra?.involved_organs) ? extra.involved_organs : []
  const fallbackSeverity = normalizeBodyMapSeverity(extra?.severity || 'warning')
  for (const rawKey of involved) {
    const key = normalizeBodyMapOrganKey(rawKey)
    if (!key) continue
    if (bodyMapSeverityRank(fallbackSeverity) > bodyMapSeverityRank(rows[key])) {
      rows[key] = fallbackSeverity
    }
  }
  return rows
}

export function buildOrganStateMapFromAiRiskExtra(extra: any) {
  const rows = createEmptyOrganStateMap()
  const organAssessment = extra?.organ_assessment && typeof extra.organ_assessment === 'object'
    ? extra.organ_assessment
    : {}
  for (const [rawKey, rawValue] of Object.entries(organAssessment)) {
    const key = normalizeBodyMapOrganKey(rawKey)
    if (!key) continue
    rows[key] = bodyMapStatusToSeverity((rawValue as any)?.status)
  }
  return rows
}

export function buildPatientOrganStateFromAlerts(alerts: any[]) {
  if (!Array.isArray(alerts) || !alerts.length) return createEmptyOrganStateMap()
  const sorted = [...alerts].sort((a: any, b: any) => {
    const bt = new Date(b?.created_at || 0).getTime()
    const at = new Date(a?.created_at || 0).getTime()
    return bt - at
  })
  const compositeMaps: Array<Record<BodyMapOrganKey, BodyMapSeverity>> = []
  const aiRiskMaps: Array<Record<BodyMapOrganKey, BodyMapSeverity>> = []
  for (const row of sorted) {
    const alertType = String(row?.alert_type || '').toLowerCase()
    const extra = row?.extra && typeof row.extra === 'object' ? row.extra : {}
    if (alertType === 'multi_organ_deterioration_trend' || extra?.organ_scores) {
      compositeMaps.push(buildOrganStateMapFromCompositeExtra({ ...extra, severity: row?.severity }))
      continue
    }
    if (alertType === 'ai_risk' || extra?.organ_assessment) {
      aiRiskMaps.push(buildOrganStateMapFromAiRiskExtra(extra))
    }
  }
  return mergeOrganStateMaps(compositeMaps[0], aiRiskMaps[0])
}

export function buildOrganStateMapByPatient(alerts: any[]) {
  const grouped = new Map<string, any[]>()
  for (const row of Array.isArray(alerts) ? alerts : []) {
    const patientId = String(row?.patient_id || '').trim()
    if (!patientId) continue
    const bucket = grouped.get(patientId) || []
    bucket.push(row)
    grouped.set(patientId, bucket)
  }
  const result = new Map<string, Record<BodyMapOrganKey, BodyMapSeverity>>()
  grouped.forEach((rows, patientId) => {
    result.set(patientId, buildPatientOrganStateFromAlerts(rows))
  })
  return result
}

export function organStateMapToScores(
  map: Partial<Record<BodyMapOrganKey, BodyMapSeverity>> | null | undefined
) {
  const stateMap = mergeOrganStateMaps(map as any)
  return BODY_MAP_ORGAN_ORDER.map((key) => bodyMapSeverityRank(stateMap[key]))
}

export type BodyMapDeviceSite =
  | 'mouth'
  | 'neck'
  | 'leftChest'
  | 'rightChest'
  | 'abdomen'
  | 'pelvis'
  | 'leftArm'
  | 'rightArm'

export type BodyMapDeviceKind =
  | 'airway'
  | 'centralLine'
  | 'arterialLine'
  | 'urinary'
  | 'feeding'
  | 'drainage'
  | 'dialysis'
  | 'other'

export const BODY_MAP_DEVICE_SITE_LABELS: Record<BodyMapDeviceSite, string> = {
  mouth: '口鼻/气道',
  neck: '颈部',
  leftChest: '左胸',
  rightChest: '右胸',
  abdomen: '腹部',
  pelvis: '盆腔/会阴',
  leftArm: '左上肢',
  rightArm: '右上肢',
}

export type BodyMapDeviceMarker = {
  key: string
  label: string
  site: BodyMapDeviceSite
  kind: BodyMapDeviceKind
  severity: BodyMapSeverity
  daysText?: string
  detail?: string
  blink?: boolean
}

function dwellDaysSeverity(value: any) {
  const days = Number(value)
  if (!Number.isFinite(days) || days <= 0) return 'normal' as BodyMapSeverity
  if (days >= 7) return 'critical' as BodyMapSeverity
  if (days >= 5) return 'high' as BodyMapSeverity
  if (days >= 3) return 'warning' as BodyMapSeverity
  return 'normal' as BodyMapSeverity
}

function detectDeviceSite(type: string, name: string, site: string): BodyMapDeviceSite {
  const haystack = `${type} ${name} ${site}`.toLowerCase()
  if (/ett|气管|经口|口咽|口鼻|trache|airway/.test(haystack)) return 'mouth'
  if (/股|femoral|腹股沟/.test(haystack)) return 'pelvis'
  if (/foley|导尿|尿管|膀胱/.test(haystack)) return 'pelvis'
  if (/picc|肱静脉|桡动脉|尺动脉|radial|brachial/.test(haystack)) {
    if (/left|左/.test(haystack)) return 'leftArm'
    if (/right|右/.test(haystack)) return 'rightArm'
  }
  if (/锁骨下|subclavian|胸腔|胸管|胸膜/.test(haystack)) {
    if (/left|左/.test(haystack)) return 'leftChest'
    if (/right|右/.test(haystack)) return 'rightChest'
    return 'rightChest'
  }
  if (/cvc|颈|深静脉|中心静脉|swan|jugular/.test(haystack)) return 'neck'
  if (/left|左/.test(haystack)) return 'leftArm'
  if (/right|右/.test(haystack)) return 'rightArm'
  if (/腹|胃|肠|引流|造瘘/.test(haystack)) return 'abdomen'
  return 'rightChest'
}

function detectDeviceKind(type: string, name: string, site: string): BodyMapDeviceKind {
  const haystack = `${type} ${name} ${site}`.toLowerCase()
  if (/ett|气管|trache|airway/.test(haystack)) return 'airway'
  if (/picc|cvc|中心静脉|深静脉|swan|cvp/.test(haystack)) return 'centralLine'
  if (/arterial|动脉|a-line|radial/.test(haystack)) return 'arterialLine'
  if (/foley|导尿|尿管|膀胱/.test(haystack)) return 'urinary'
  if (/胃管|鼻饲|空肠|feeding|ng|nj|peg/.test(haystack)) return 'feeding'
  if (/透析|dialysis|crrt/.test(haystack)) return 'dialysis'
  if (/引流|drain|chest tube|胸管|造瘘/.test(haystack)) return 'drainage'
  return 'other'
}

function shortDeviceLabel(type: string, name: string) {
  const haystack = `${type} ${name}`.toLowerCase()
  if (/ett|气管|endotracheal/.test(haystack)) return 'ETT'
  if (/foley|导尿/.test(haystack)) return 'Foley'
  if (/picc/.test(haystack)) return 'PICC'
  if (/cvc|中心静脉|深静脉/.test(haystack)) return 'CVC'
  if (/arterial|动脉/.test(haystack)) return 'A-line'
  return String(name || type || '导管').slice(0, 10)
}

export function buildDeviceMarkers(payload: {
  alerts?: any[]
  bedcard?: any
}) {
  const markers: BodyMapDeviceMarker[] = []
  const seen = new Set<string>()
  const tubes = Array.isArray(payload?.bedcard?.tubes) ? payload.bedcard.tubes : []
  for (const row of tubes) {
    const name = String(row?.name || '').trim()
    const category = String(row?.category || '').trim()
    const siteText = String(row?.site || '').trim()
    const dwellDays = Number(row?.dwellDays)
    const marker: BodyMapDeviceMarker = {
      key: `${name}-${category}-${siteText}` || `tube-${markers.length}`,
      label: shortDeviceLabel(category, name),
      site: detectDeviceSite(category, name, siteText),
      kind: detectDeviceKind(category, name, siteText),
      severity: dwellDaysSeverity(dwellDays),
      daysText: Number.isFinite(dwellDays) ? `D${dwellDays}` : '',
      detail: name || category || '留置装置',
      blink: Number.isFinite(dwellDays) && dwellDays >= 7,
    }
    markers.push(marker)
    seen.add(marker.label.toLowerCase())
  }

  const deviceAlerts = Array.isArray(payload?.alerts)
    ? payload.alerts.filter((row: any) => String(row?.category || '').toLowerCase() === 'device_management')
    : []
  for (const alert of deviceAlerts) {
    const extra = alert?.extra && typeof alert.extra === 'object' ? alert.extra : {}
    const type = String(extra?.type || alert?.alert_type || '').trim()
    const label = shortDeviceLabel(type, alert?.name || type)
    if (!label || seen.has(label.toLowerCase())) continue
    const lineDays = Number(extra?.line_days)
    markers.push({
      key: `${label}-${markers.length}`,
      label,
      site: detectDeviceSite(type, label, extra?.site || ''),
      kind: detectDeviceKind(type, label, extra?.site || ''),
      severity: normalizeBodyMapSeverity(alert?.severity || dwellDaysSeverity(lineDays)),
      daysText: Number.isFinite(lineDays) ? `D${lineDays}` : '',
      detail: String(alert?.name || type || '装置管理提醒'),
      blink: normalizeBodyMapSeverity(alert?.severity) === 'critical' || lineDays >= 7,
    })
    seen.add(label.toLowerCase())
  }
  return markers
}
