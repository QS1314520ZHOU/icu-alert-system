import { describe, expect, it } from 'vitest'
import { normalizeOrganAlarmMessage } from '../../src/services/humanBodyAlarmAdapter'

describe('humanBodyAlarmAdapter', () => {
  it('normalizes organ_alarm socket messages into store payloads', () => {
    const normalized = normalizeOrganAlarmMessage({
      type: 'organ_alarm',
      data: {
        organ: 'heart',
        severity: 'high',
        metric_name: 'MAP',
        metric_value: 52,
        patient_id: 'p1',
        patient_name: '王某',
        bed_no: '08',
        timestamp: 123,
      },
    })

    expect(normalized).toEqual({
      organ: 'heart',
      payload: {
        level: 'critical',
        metric: 'MAP',
        value: 52,
        patientId: 'p1',
        patientName: '王某',
        bed: '08',
        timestamp: 123,
        source: 'alert_socket',
      },
    })
  })

  it('ignores messages without a known organ', () => {
    expect(normalizeOrganAlarmMessage({ type: 'organ_alarm', data: { organ: 'unknown' } })).toBeNull()
  })
})
