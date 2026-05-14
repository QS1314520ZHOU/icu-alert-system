import type { OrganBusinessName } from './organ'

export type HumanBodyAlarmLevel = 'critical' | 'warning' | 'info' | 'selected'

export type HumanBodyAlarmPayload = {
  level: HumanBodyAlarmLevel
  metric?: string
  value?: string | number | null
  timestamp?: number
  patientId?: string
  patientName?: string
  bed?: string
  source?: string
}

export type HumanBodyAlarmRecord = HumanBodyAlarmPayload & {
  organ: OrganBusinessName
  timestamp: number
}

export type HumanBodyAlarmInput = Omit<HumanBodyAlarmPayload, 'level'> & {
  level?: HumanBodyAlarmLevel | string
}
