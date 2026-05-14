import { subscribeAlertSocket, type AlertSocketMessage } from './alertSocket'
import { ORGAN_MAP, isKnownOrgan } from '../components/HumanBody/constants/organMap'
import { normalizeAlarmLevel } from '../components/HumanBody/constants/alarmLevels'
import { useHumanBodyAlarmStore } from '../stores/humanBodyAlarmStore'
import type { HumanBodyAlarmInput } from '../types/alarm'
import type { OrganBusinessName } from '../types/organ'

const MOCK_INTERVAL_MS = 8000
const MOCK_ORGANS = Object.keys(ORGAN_MAP) as OrganBusinessName[]
const MOCK_LEVELS = ['critical', 'warning', 'info'] as const

function text(value: unknown): string | undefined {
  const normalized = String(value || '').trim()
  return normalized || undefined
}

function numberOrText(value: unknown): string | number | null | undefined {
  if (value === null || value === undefined || value === '') return value as null | undefined
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric : String(value)
}

export function normalizeOrganAlarmMessage(message: AlertSocketMessage | Record<string, any>): {
  organ: OrganBusinessName
  payload: HumanBodyAlarmInput
} | null {
  // TODO: align organ_alarm wire shape with backend.
  const data = (message as AlertSocketMessage)?.data || message || {}
  const organ = text(data.organ || data.organ_name || data.organName)
  if (!organ || !isKnownOrgan(organ)) return null

  return {
    organ,
    payload: {
      level: normalizeAlarmLevel(data.level || data.severity || data.alarm_level),
      metric: text(data.metric || data.metric_name || data.rule_name),
      value: numberOrText(data.value ?? data.metric_value),
      patientId: text(data.patientId || data.patient_id),
      patientName: text(data.patientName || data.patient_name),
      bed: text(data.bed || data.bed_no || data.bedNo),
      timestamp: Number(data.timestamp || data.occurred_at || Date.now()),
      source: text(data.source || 'alert_socket'),
    },
  }
}

export function connectHumanBodyAlarmAdapter() {
  const store = useHumanBodyAlarmStore()
  if (import.meta.env.VITE_USE_MOCK === 'true') {
    const timer = window.setInterval(() => {
      const organ = MOCK_ORGANS[Math.floor(Math.random() * MOCK_ORGANS.length)] || 'heart'
      const level = MOCK_LEVELS[Math.floor(Math.random() * MOCK_LEVELS.length)] || 'info'
      store.setAlarm(organ, {
        level,
        metric: level === 'critical' ? 'MAP' : level === 'warning' ? 'SpO2' : 'HR',
        value: level === 'critical' ? 52 : level === 'warning' ? 88 : 112,
        patientId: `mock-${Math.floor(Math.random() * 6) + 1}`,
        patientName: '演示患者',
        bed: `${Math.floor(Math.random() * 12) + 1}`,
        source: 'mock',
      })
    }, MOCK_INTERVAL_MS)
    return () => window.clearInterval(timer)
  }

  return subscribeAlertSocket('organ_alarm', (message) => {
    const normalized = normalizeOrganAlarmMessage(message)
    if (!normalized) return
    store.setAlarm(normalized.organ, normalized.payload)
  })
}
