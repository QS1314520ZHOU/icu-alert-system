import { describe, expect, it } from 'vitest'
import { buildBundleRows, buildWindows, bundleHeadline } from '../components/sepsis/sepsisBundleModel'

const T0 = Date.parse('2026-10-30T10:00:00')
const iso = (min: number) => new Date(T0 + min * 60000).toISOString()
const base = (elements: any) => ({
  status: 'pending', bundle_started_at: iso(0), deadline_1h: iso(60), deadline_3h: iso(180), bundle_elements: elements,
})

describe('sepsisBundleModel', () => {
  it('时窗未结束显示“待”，不判未达标', () => {
    const s = base({ antibiotic_assessment: { applicability: 'required', execution: { status: 'pending' } } })
    const rows = buildBundleRows(s, T0 + 30 * 60000)
    expect(rows[0]!.mark).toBe('待')
    expect(rows[0]!.tone).toBe('wait')
    expect(buildWindows(s, T0 + 30 * 60000)[0]!.label).toBe('剩 30m')
  })
  it('超过时窗仍未执行判为超时', () => {
    const s = base({ antibiotic_assessment: { applicability: 'required', execution: { status: 'pending' } } })
    const rows = buildBundleRows(s, T0 + 70 * 60000)
    expect(rows[0]!.tone).toBe('fail')
    expect(bundleHeadline(s, rows, T0 + 70 * 60000).text).toContain('已超时')
  })
  it('未取到记录显示“—”，不按未完成计', () => {
    const s = base({ blood_culture: { applicability: 'required', execution: { status: 'data_missing' } } })
    const rows = buildBundleRows(s, T0 + 70 * 60000)
    expect(rows[0]!.mark).toBe('—')
    expect(rows[0]!.tone).toBe('none')
  })
  it('抗菌药早于血培养给出提示', () => {
    const s = base({
      blood_culture: { applicability: 'required', execution: { status: 'met', completed_at: iso(30) } },
      antibiotic_assessment: { applicability: 'required', execution: { status: 'met', completed_at: iso(20) } },
    })
    const bc = buildBundleRows(s, T0 + 40 * 60000).find((r) => r.key === 'blood_culture')!
    expect(bc.note).toContain('抗菌药早于血培养')
  })
  it('乳酸≥2 超过 2h 未复测提示需复测', () => {
    const s = base({
      lactate: { applicability: 'required', execution: { status: 'met', completed_at: iso(5), value: '3.1' } },
      lactate_repeat: { applicability: 'conditional', execution: { status: 'pending' } },
    })
    const rep = buildBundleRows(s, T0 + 150 * 60000).find((r) => r.key === 'lactate_repeat')!
    expect(rep.note).toContain('需复测')
  })
})
