import { computed, type Ref } from 'vue'

export type OrganKey = 'lung' | 'heart' | 'liver' | 'kidney' | 'brain' | 'coag'

export type OrganState = {
  key: OrganKey
  label: string
  severity: number        // 0-1
  sofa: number | null     // 0-4
  source: 'sofa' | 'derived' | 'none'
  metrics: Array<{ label: string; value: string }>
}

const N = (v: any, max = 4): number => {
  const n = Number(v)
  if (!Number.isFinite(n)) return 0
  return Math.min(1, Math.max(0, n / max))
}

const fmt = (v: any, unit = '', dp?: number): string => {
  if (v == null || v === '') return '—'
  const n = Number(v)
  if (!Number.isFinite(n)) return String(v)
  return dp != null ? n.toFixed(dp) + unit : String(Math.round(n)) + unit
}

export function useOrganSeverity(twinSnapshot: Ref<any>) {
  return computed<OrganState[]>(() => {
    const t = twinSnapshot.value
    if (!t) return []

    const pick = (...keys: string[]): number | null => {
      for (const k of keys) {
        const v = t?.sofa?.[k] ?? t?.scores?.[k]
        if (v != null) return Number(v)
      }
      return null
    }

    const build = (
      key: OrganKey,
      label: string,
      sofa: number | null,
      severity: number | null,
      source: OrganState['source'],
      metrics: Array<{ label: string; value: string }>,
    ): OrganState => ({
      key,
      label,
      severity: severity != null ? Math.min(1, Math.max(0, severity)) : 0,
      sofa: sofa != null ? Math.round(sofa) : null,
      source: sofa != null ? 'sofa' : source,
      metrics,
    })

    const brainDerived = t?.neuro?.rass != null ? N(t.neuro.rass, 4) : null
    const kidneyDerived = t?.labs?.latest?.cr?.value != null ? N(t.labs.latest.cr.value, 4) : null
    const lungDerived = t?.ventilation?.pf_ratio != null
      ? Math.min(1, Math.max(0, 1 - Number(t.ventilation.pf_ratio) / 300))
      : null
    const uo = t?.output?.urine?.rate

    return [
      build('lung', '肺',
        pick('respiratory'), lungDerived, 'derived',
        [{ label: 'P/F', value: fmt(t?.ventilation?.pf_ratio, '', 0) },
         { label: 'FiO₂', value: fmt(t?.ventilation?.fio2, '%', 0) }]),

      build('heart', '心脏',
        pick('cardiovascular'), null, 'derived',
        [{ label: 'MAP', value: fmt(t?.vitals?.map?.value, ' mmHg', 0) },
         { label: 'HR', value: fmt(t?.vitals?.hr?.value, ' bpm', 0) }]),

      build('brain', '神经',
        pick('cns', 'neurological'), brainDerived, 'derived',
        [{ label: 'RASS', value: fmt(t?.neuro?.rass, '', 0) },
         { label: 'GCS', value: fmt(t?.neuro?.gcs, '', 0) }]),

      build('liver', '肝脏',
        pick('hepatic'), null, 'derived',
        [{ label: '总胆红素', value: fmt(t?.labs?.latest?.tbil?.value, ' μmol/L') }]),

      build('kidney', '肾脏',
        pick('renal', 'kidney'), kidneyDerived, 'derived',
        [{ label: '肌酐', value: fmt(t?.labs?.latest?.cr?.value, ' μmol/L', 0) },
         { label: '尿量', value: fmt(uo, ' mL/kg/h', 2) }]),

      build('coag', '凝血',
        pick('coagulation', 'coag', 'platelet'), null, 'derived',
        [{ label: '血小板', value: fmt(t?.labs?.latest?.plt?.value, ' ×10⁹/L', 0) },
         { label: 'INR', value: fmt(t?.labs?.latest?.inr?.value, '', 2) }]),
    ]
  })
}