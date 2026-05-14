import { describe, expect, it } from 'vitest'
import { ALARM_LEVELS, alarmPriority, normalizeAlarmLevel } from '../../src/components/HumanBody/constants/alarmLevels'

describe('ALARM_LEVELS', () => {
  it('exports medical alarm colors and blink rates', () => {
    expect(ALARM_LEVELS.critical.color).toBe(0xff2222)
    expect(ALARM_LEVELS.critical.blinkHz).toBe(2)
    expect(ALARM_LEVELS.warning.priority).toBeGreaterThan(ALARM_LEVELS.info.priority)
    expect(ALARM_LEVELS.selected.blinkHz).toBe(0)
  })

  it('normalizes backend severity aliases', () => {
    expect(normalizeAlarmLevel('high')).toBe('critical')
    expect(normalizeAlarmLevel('warn')).toBe('warning')
    expect(normalizeAlarmLevel('medium')).toBe('info')
    expect(normalizeAlarmLevel('selected')).toBe('selected')
  })

  it('returns priority for known levels', () => {
    expect(alarmPriority('critical')).toBe(3)
    expect(alarmPriority('missing')).toBe(-1)
  })
})
