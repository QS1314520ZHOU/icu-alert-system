import { defineStore } from 'pinia'
import { alarmPriority, normalizeAlarmLevel } from '../components/HumanBody/constants/alarmLevels'
import { isKnownOrgan } from '../components/HumanBody/constants/organMap'
import type { HumanBodyAlarmInput, HumanBodyAlarmRecord } from '../types/alarm'
import type { OrganBusinessName } from '../types/organ'

type AlarmState = {
  alarms: Record<string, HumanBodyAlarmRecord>
}

const AGGREGATE_KEY = 'aggregate'

function normalizePatientId(value: unknown): string {
  return String(value || '').trim()
}

function alarmKey(organ: OrganBusinessName, patientId?: string | null): string {
  const scope = normalizePatientId(patientId) || AGGREGATE_KEY
  return `${scope}:${organ}`
}

function sortAlarms(records: HumanBodyAlarmRecord[]): HumanBodyAlarmRecord[] {
  return [...records].sort((a, b) => {
    const priorityDelta = alarmPriority(b.level) - alarmPriority(a.level)
    if (priorityDelta !== 0) return priorityDelta
    return (b.timestamp || 0) - (a.timestamp || 0)
  })
}

function byPatientId(record: HumanBodyAlarmRecord, patientId: string): boolean {
  return normalizePatientId(record.patientId) === patientId
}

export const useHumanBodyAlarmStore = defineStore('humanBodyAlarm', {
  state: (): AlarmState => ({
    alarms: {},
  }),
  getters: {
    activeAlarms(state): HumanBodyAlarmRecord[] {
      return sortAlarms(Object.values(state.alarms))
    },
    highestPriorityOrgan(): OrganBusinessName | null {
      return this.activeAlarms[0]?.organ || null
    },
    getAlarmsByPatient: state => (id: string): HumanBodyAlarmRecord[] => {
      const patientId = normalizePatientId(id)
      if (!patientId) return []
      return sortAlarms(Object.values(state.alarms).filter(record => byPatientId(record, patientId)))
    },
    getAggregatedAlarms: state => (): HumanBodyAlarmRecord[] => {
      const highestByOrgan = new Map<OrganBusinessName, HumanBodyAlarmRecord>()
      Object.values(state.alarms).forEach((record) => {
        const current = highestByOrgan.get(record.organ)
        if (!current) {
          highestByOrgan.set(record.organ, record)
          return
        }
        const priorityDelta = alarmPriority(record.level) - alarmPriority(current.level)
        if (priorityDelta > 0 || (priorityDelta === 0 && record.timestamp > current.timestamp)) {
          highestByOrgan.set(record.organ, record)
        }
      })
      return sortAlarms([...highestByOrgan.values()])
    },
    getHighestPriorityOrgan() {
      return (patientId?: string | null): OrganBusinessName | null => {
        const scoped = normalizePatientId(patientId)
        const records = scoped ? this.getAlarmsByPatient(scoped) : this.getAggregatedAlarms()
        return records[0]?.organ || null
      }
    },
  },
  actions: {
    setAlarm(organ: string, payload: HumanBodyAlarmInput = {}) {
      if (!isKnownOrgan(organ)) return
      const knownOrgan = organ as OrganBusinessName
      const patientId = normalizePatientId(payload.patientId)
      const record: HumanBodyAlarmRecord = {
        organ: knownOrgan,
        level: normalizeAlarmLevel(payload.level),
        metric: payload.metric,
        value: payload.value,
        patientId: patientId || undefined,
        patientName: payload.patientName,
        bed: payload.bed,
        timestamp: Number(payload.timestamp || Date.now()),
        source: payload.source,
      }
      this.alarms[alarmKey(knownOrgan, patientId)] = record
    },
    clearAlarm(organ: string, patientId?: string | null) {
      if (!isKnownOrgan(organ)) return
      const scoped = normalizePatientId(patientId)
      if (scoped) {
        delete this.alarms[alarmKey(organ as OrganBusinessName, scoped)]
        return
      }
      Object.keys(this.alarms).forEach((key) => {
        if (key.endsWith(`:${organ}`)) delete this.alarms[key]
      })
    },
    clearAll(patientId?: string | null) {
      const scoped = normalizePatientId(patientId)
      if (!scoped) {
        this.alarms = {}
        return
      }
      Object.entries(this.alarms).forEach(([key, record]) => {
        if (byPatientId(record, scoped)) delete this.alarms[key]
      })
    },
  },
})

