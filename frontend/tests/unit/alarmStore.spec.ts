import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useHumanBodyAlarmStore } from '../../src/stores/humanBodyAlarmStore'

describe('humanBodyAlarmStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('sets and updates a known organ alarm', () => {
    const store = useHumanBodyAlarmStore()

    store.setAlarm('heart', { level: 'warning', metric: 'HR', value: 130, patientId: 'p1' })
    store.setAlarm('heart', { level: 'critical', metric: 'MAP', value: 52, patientId: 'p1' })

    expect(store.activeAlarms).toHaveLength(1)
    expect(store.activeAlarms[0]).toMatchObject({
      organ: 'heart',
      level: 'critical',
      metric: 'MAP',
      value: 52,
      patientId: 'p1',
    })
  })

  it('ignores unknown organs', () => {
    const store = useHumanBodyAlarmStore()

    store.setAlarm('unknown', { level: 'critical' })

    expect(store.activeAlarms).toHaveLength(0)
  })

  it('sorts active alarms by level priority and timestamp', () => {
    const store = useHumanBodyAlarmStore()

    store.setAlarm('liver', { level: 'info', timestamp: 300 })
    store.setAlarm('brain', { level: 'critical', timestamp: 100 })
    store.setAlarm('heart', { level: 'critical', timestamp: 400 })
    store.setAlarm('left_lung', { level: 'warning', timestamp: 500 })

    expect(store.activeAlarms.map(item => item.organ)).toEqual(['heart', 'brain', 'left_lung', 'liver'])
    expect(store.highestPriorityOrgan).toBe('heart')
  })

  it('clears one alarm by organ and patient', () => {
    const store = useHumanBodyAlarmStore()

    store.setAlarm('heart', { level: 'critical', patientId: 'p1' })
    store.setAlarm('heart', { level: 'warning', patientId: 'p2' })
    store.clearAlarm('heart', 'p1')

    expect(store.activeAlarms).toHaveLength(1)
    expect(store.activeAlarms[0]?.patientId).toBe('p2')
  })

  it('clears all alarms globally or by patient', () => {
    const store = useHumanBodyAlarmStore()

    store.setAlarm('heart', { level: 'critical', patientId: 'p1' })
    store.setAlarm('brain', { level: 'warning', patientId: 'p2' })
    store.clearAll('p1')

    expect(store.activeAlarms.map(item => item.patientId)).toEqual(['p2'])

    store.clearAll()
    expect(store.activeAlarms).toHaveLength(0)
  })

  it('returns patient scoped alarms', () => {
    const store = useHumanBodyAlarmStore()

    store.setAlarm('heart', { level: 'critical', patientId: 'p1' })
    store.setAlarm('brain', { level: 'warning', patientId: 'p2' })

    expect(store.getAlarmsByPatient('p1').map(item => item.organ)).toEqual(['heart'])
    expect(store.getHighestPriorityOrgan('p2')).toBe('brain')
  })

  it('aggregates highest priority alarm per organ across patients', () => {
    const store = useHumanBodyAlarmStore()

    store.setAlarm('heart', { level: 'warning', patientId: 'p1', timestamp: 100 })
    store.setAlarm('heart', { level: 'critical', patientId: 'p2', timestamp: 200 })
    store.setAlarm('brain', { level: 'info', patientId: 'p3', timestamp: 300 })

    const aggregated = store.getAggregatedAlarms()

    expect(aggregated).toHaveLength(2)
    expect(aggregated[0]).toMatchObject({ organ: 'heart', level: 'critical', patientId: 'p2' })
    expect(store.getHighestPriorityOrgan()).toBe('heart')
  })
})

