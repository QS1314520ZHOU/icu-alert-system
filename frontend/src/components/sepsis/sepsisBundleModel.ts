/**
 * 脓毒症集束化（Hour-1 / 3h）床旁时间轴模型。
 * 借鉴 icu-sepsis-intelligence 的 ICU-05 判定展示：三态（✓ / × / —），
 * “—”表示无法判定，不按未完成计；时窗未到截止时间只显示“待 · 剩 xx”，不判未达标。
 * 仅用于展示，不改变后端判定。
 */
export type CellTone = 'done' | 'late' | 'fail' | 'wait' | 'none' | 'quiet'
export interface BundleRow {
  key: string
  name: string
  window: '1h' | '3h'
  mark: string
  tone: CellTone
  time: string | null
  note: string
}
export interface BundleWindow { key: '1h' | '3h'; deadline: string | null; remainingSec: number | null; label: string; tone: CellTone }

const ELEMENT_DEFS: { keys: string[]; name: string; window: '1h' | '3h' }[] = [
  { keys: ['lactate'], name: '乳酸测定', window: '1h' },
  { keys: ['blood_culture'], name: '血培养（抗菌药前）', window: '1h' },
  { keys: ['first_antibiotic', 'antibiotic_assessment', 'antibiotic'], name: '广谱抗菌药物', window: '1h' },
  { keys: ['vasopressor'], name: '血管活性药（MAP<65）', window: '1h' },
  { keys: ['fluid_resuscitation'], name: '晶体液 30 ml/kg', window: '3h' },
  { keys: ['lactate_repeat'], name: '复测乳酸（初值≥2）', window: '3h' },
  { keys: ['infection_source'], name: '感染源评估/控制', window: '3h' },
]

export const APPLICABILITY_TEXT: Record<string, string> = {
  required: '必需', conditional: '条件触发', not_applicable: '不适用', review_pending: '待医生判断适用性',
  contraindicated: '禁忌', individualized: '个体化',
}

function toMs(t: unknown): number | null {
  if (!t) return null
  const n = Date.parse(String(t))
  return Number.isFinite(n) ? n : null
}
export function fmtRemain(sec: number): string {
  const m = Math.max(0, Math.round(sec / 60))
  if (m >= 60) return `${Math.floor(m / 60)}h${m % 60 ? `${m % 60}m` : ''}`
  return `${m}m`
}
export function fmtHm(t: unknown): string {
  const ms = toMs(t)
  if (ms == null) return ''
  const d = new Date(ms)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

export function buildWindows(status: any, now: number): BundleWindow[] {
  return (['1h', '3h'] as const).map((key) => {
    const deadline = status?.[`deadline_${key}`] || null
    const dl = toMs(deadline)
    const remainingSec = dl == null ? null : Math.floor((dl - now) / 1000)
    const st = String(status?.status || '')
    let label = '无截止时间'
    let tone: CellTone = 'none'
    if (st === 'met' && key === '1h') { label = '已达标'; tone = 'done' }
    else if (st === 'met_late' && key === '1h') { label = '补执行（超时）'; tone = 'late' }
    else if (remainingSec != null) {
      if (remainingSec > 0) { label = `剩 ${fmtRemain(remainingSec)}`; tone = remainingSec <= 15 * 60 ? 'late' : 'wait' }
      else { label = `已超 ${fmtRemain(-remainingSec)}`; tone = 'fail' }
    }
    return { key, deadline, remainingSec, label, tone }
  })
}

export function buildBundleRows(status: any, now: number): BundleRow[] {
  const elements = status?.bundle_elements
  if (!elements || typeof elements !== 'object') return []
  const windows = buildWindows(status, now)
  const rows: BundleRow[] = []
  for (const def of ELEMENT_DEFS) {
    const key = def.keys.find((k) => elements[k])
    if (!key) continue
    const el = elements[key] || {}
    const exec = (el.execution && typeof el.execution === 'object') ? el.execution : el
    const ex = String(exec?.status || 'pending').toLowerCase()
    const app = String(el.applicability || '').toLowerCase()
    const time = exec?.completed_at || null
    const w = windows.find((x) => x.key === def.window)!
    const notes: string[] = []
    if (exec?.value != null && exec.value !== '') notes.push(String(exec.value))
    if (exec?.antibiotic_name) notes.push(String(exec.antibiotic_name))
    let mark = '—'
    let tone: CellTone = 'none'
    if (app === 'not_applicable') { mark = '不适用'; tone = 'quiet' }
    else if (ex === 'met' || ex === 'completed_before') { mark = '✓'; tone = 'done'; if (ex === 'completed_before') notes.push('计时前已完成') }
    else if (ex === 'met_late') { mark = '✓ 超时'; tone = 'late' }
    else if (ex === 'cancelled') { mark = '已取消'; tone = 'quiet' }
    else if (ex === 'data_missing') { mark = '—'; tone = 'none'; notes.push('未取到记录，不按未完成计') }
    else if (w.remainingSec == null) { mark = '待'; tone = 'wait' }
    else if (w.remainingSec > 0) { mark = '待'; tone = 'wait'; notes.push(`${def.window} 窗口剩 ${fmtRemain(w.remainingSec)}`) }
    else { mark = '× 超时'; tone = 'fail' }
    if (app === 'review_pending' && tone !== 'done') notes.push('适用性待医生判断')
    if (app === 'conditional') {
      const trig = el?.condition?.trigger_evidence
      if (Array.isArray(trig) && trig.length) notes.push(`触发：${trig.join('、')}`)
    }
    rows.push({ key, name: def.name, window: def.window, mark, tone, time, note: notes.join(' · ') })
  }
  // 先培养后抗菌：两者都有时间且抗菌药更早 → 提示
  const bc = elements.blood_culture?.execution?.completed_at
  const abEl = elements.first_antibiotic || elements.antibiotic_assessment || elements.antibiotic
  const ab = abEl?.execution?.completed_at
  const bcMs = toMs(bc)
  const abMs = toMs(ab)
  if (bcMs != null && abMs != null && abMs < bcMs) {
    const r = rows.find((x) => x.key === 'blood_culture')
    if (r) { r.tone = r.tone === 'done' ? 'late' : r.tone; r.note = [r.note, '抗菌药早于血培养'].filter(Boolean).join(' · ') }
  }
  // 乳酸 ≥2 且距首测 >2h 未复测 → 需复测
  const lac = Number(elements.lactate?.execution?.value ?? status?.lactate)
  const lacMs = toMs(elements.lactate?.execution?.completed_at)
  const rep = rows.find((x) => x.key === 'lactate_repeat')
  if (rep && rep.tone !== 'done' && Number.isFinite(lac) && lac >= 2 && lacMs != null && now - lacMs > 2 * 3600_000) {
    rep.note = [rep.note, `首测 ${lac} 已过 ${Math.floor((now - lacMs) / 3600_000)}h，需复测`].filter(Boolean).join(' · ')
    if (rep.tone === 'wait') rep.tone = 'late'
  }
  return rows
}

/** 一句话结论：先说最该做的事 */
export function bundleHeadline(status: any, rows: BundleRow[], now: number): { text: string; tone: CellTone } {
  const st = String(status?.status || 'none')
  if (st === 'none') return { text: '未进入脓毒症集束化计时', tone: 'quiet' }
  if (st === 'met') return { text: 'Hour-1 集束化已按时完成', tone: 'done' }
  const w1 = buildWindows(status, now)[0]!
  const overdue = rows.filter((r) => r.tone === 'fail')
  const waiting = rows.filter((r) => r.tone === 'wait' || (r.tone === 'late' && r.mark === '待'))
  if (overdue.length) return { text: `${overdue.map((r) => r.name).join('、')} 已超时未完成`, tone: 'fail' }
  if (waiting.length) {
    const remain = w1.remainingSec != null && w1.remainingSec > 0 ? `，1h 窗口剩 ${fmtRemain(w1.remainingSec)}` : ''
    return { text: `待完成：${waiting.map((r) => r.name).join('、')}${remain}`, tone: w1.tone === 'late' ? 'late' : 'wait' }
  }
  if (st === 'met_late') return { text: '集束化已补执行，但超过 1h 时限', tone: 'late' }
  return { text: String(status?.label || '集束化计时中'), tone: 'wait' }
}
