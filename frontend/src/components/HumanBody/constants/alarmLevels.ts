import type { HumanBodyAlarmLevel } from '../../../types/alarm'

export type AlarmLevelConfig = {
  color: number
  emissive: number
  blinkHz: number
  priority: number
  cssColor: string
}

export const ALARM_LEVELS: Record<HumanBodyAlarmLevel, AlarmLevelConfig> = {
  critical: { color: 0xff2222, emissive: 0xff0000, blinkHz: 2.0, priority: 3, cssColor: '#ff2222' },
  warning: { color: 0xffaa00, emissive: 0xff8800, blinkHz: 1.0, priority: 2, cssColor: '#ffaa00' },
  info: { color: 0xffee44, emissive: 0xffcc00, blinkHz: 0.5, priority: 1, cssColor: '#ffee44' },
  selected: { color: 0x00e5ff, emissive: 0x00aaff, blinkHz: 0, priority: 0, cssColor: '#00e5ff' },
}

export function alarmPriority(level: string | undefined | null): number {
  return ALARM_LEVELS[level as HumanBodyAlarmLevel]?.priority ?? -1
}

export function normalizeAlarmLevel(level: unknown): HumanBodyAlarmLevel {
  const raw = String(level || '').trim().toLowerCase()
  if (raw === 'critical' || raw === 'red' || raw === 'high') return 'critical'
  if (raw === 'warning' || raw === 'warn' || raw === 'orange') return 'warning'
  if (raw === 'info' || raw === 'yellow' || raw === 'medium' || raw === 'low') return 'info'
  if (raw === 'selected') return 'selected'
  return 'info'
}
