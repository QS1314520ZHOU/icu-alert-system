/**
 * groupAlerts.ts
 * 预警合并归组工具 —— 将同一患者短时间内触发的相关预警聚合为复合预警包
 * 聚合维度：patient_id + 5 分钟时间窗 + 生理系统分类
 */

export type AlertSeverity = 'critical' | 'warning' | 'info'

export interface RawAlert {
  _id?: string
  rule_id?: string
  alert_type?: string
  patient_id?: string
  patient_name?: string
  bed?: string | number
  severity?: string
  category?: string
  name?: string
  created_at?: string | Date
  [key: string]: any
}

export interface AlertGroup {
  /** 唯一标识，用于 v-for key */
  groupKey: string
  /** 聚合后展示的系统标签，如「血流动力学」 */
  systemLabel: string
  /** 组内最高级别 */
  severity: AlertSeverity
  /** 患者信息（取第一条） */
  patient_id: string
  patient_name: string
  bed: string
  /** 最新触发时间 */
  created_at: string | Date | undefined
  /** 组内所有原始预警（≥2 条时为聚合包，=1 条时为普通单条） */
  alerts: RawAlert[]
  /** 是否为聚合包（多条合并） */
  isGroup: boolean
}

// ── 生理系统分类映射 ────────────────────────────────────────────
const SYSTEM_MAP: Array<{ label: string; keywords: string[] }> = [
  {
    label: '血流动力学',
    keywords: ['map', 'hr', 'heart_rate', 'lactate', 'lac', 'shock', 'hemodynamic', 'sbp', 'dbp', 'bp', 'cardiac'],
  },
  {
    label: '呼吸 / 氧合',
    keywords: ['spo2', 'rr', 'resp', 'hypoxia', 'pip', 'peep', 'fio2', 'vent', 'weaning', 'extub', 'oxygen'],
  },
  {
    label: '感染 / 脓毒症',
    keywords: ['sepsis', 'infection', 'antibiotic', 'microb', 'procalcitonin', 'pct', 'wbc', 'fever', 'temperature'],
  },
  {
    label: '代谢 / 肾脏',
    keywords: ['creatinine', 'cr', 'potassium', 'sodium', 'glucose', 'glycemic', 'aki', 'renal', 'electrolyte'],
  },
  {
    label: '凝血 / 出血',
    keywords: ['bleed', 'coag', 'pt', 'inr', 'plt', 'platelet', 'dic', 'thromb'],
  },
  {
    label: '神经 / 镇静',
    keywords: ['neuro', 'sedation', 'rass', 'cam', 'delirium', 'gcs', 'pain', 'analgesia'],
  },
]

const SEVERITY_ORDER: Record<string, number> = {
  critical: 3,
  warning: 2,
  info: 1,
}

function classifySystem(alert: RawAlert): string {
  const haystack = [
    alert.rule_id || '',
    alert.alert_type || '',
    alert.category || '',
    alert.name || '',
  ]
    .join(' ')
    .toLowerCase()

  for (const { label, keywords } of SYSTEM_MAP) {
    if (keywords.some((k) => haystack.includes(k))) return label
  }
  return '其他'
}

function maxSeverity(alerts: RawAlert[]): AlertSeverity {
  let max = 0
  let result: AlertSeverity = 'info'
  for (const a of alerts) {
    const s = a.severity || 'info'
    const rank = SEVERITY_ORDER[s] ?? 1
    if (rank > max) {
      max = rank
      result = s as AlertSeverity
    }
  }
  return result
}

function toMs(val: string | Date | undefined): number {
  if (!val) return 0
  if (val instanceof Date) return val.getTime()
  const d = new Date(val)
  return isNaN(d.getTime()) ? 0 : d.getTime()
}

/**
 * 将平铺的预警列表聚合为 AlertGroup[]
 * @param alerts  原始预警列表（已按时间/优先级排序）
 * @param windowMs 聚合时间窗，默认 5 分钟（300_000 ms）
 */
export function groupAlerts(
  alerts: RawAlert[],
  windowMs = 5 * 60 * 1000,
): AlertGroup[] {
  if (!alerts || alerts.length === 0) return []

  // 按 patient_id + system 聚合
  // key: `{patient_id}|{system}|{timeSlot}`
  const buckets = new Map<string, RawAlert[]>()

  for (const alert of alerts) {
    const pid = String(alert.patient_id || alert.bed || '_')
    const system = classifySystem(alert)
    const ts = toMs(alert.created_at as string | Date | undefined)
    // 将时间槽对齐到 windowMs 的倍数
    const slot = windowMs > 0 ? Math.floor(ts / windowMs) : 0
    const key = `${pid}|${system}|${slot}`

    if (!buckets.has(key)) buckets.set(key, [])
    buckets.get(key)!.push(alert)
  }

  const groups: AlertGroup[] = []

  for (const [key, items] of buckets) {
    if (!items.length) continue
    // 按时间降序取最新
    items.sort((a, b) => toMs(b.created_at as any) - toMs(a.created_at as any))
    const first = items[0]
    if (!first) continue
    const system = classifySystem(first)

    groups.push({
      groupKey: key,
      systemLabel: system,
      severity: maxSeverity(items),
      patient_id: String(first.patient_id || ''),
      patient_name: String(first.patient_name || '未知患者'),
      bed: String(first.bed || '--'),
      created_at: first.created_at,
      alerts: items,
      isGroup: items.length > 1,
    })
  }

  // 组间排序：severity desc → 时间 desc
  groups.sort((a, b) => {
    const sd = (SEVERITY_ORDER[b.severity] ?? 0) - (SEVERITY_ORDER[a.severity] ?? 0)
    if (sd !== 0) return sd
    return toMs(b.created_at as any) - toMs(a.created_at as any)
  })

  return groups
}
