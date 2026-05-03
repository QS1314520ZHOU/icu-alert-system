import { defineStore } from 'pinia'
import { onAlertMessage, sendAlertSocketMessage } from '../services/alertSocket'

export type PulseNarration = {
  candidate_id: string
  patient_id: string
  headline: string
  action_hint: string
  tone: 'info' | 'warn' | 'critical'
  deep_link: string
  source: string
  occurred_at: string
}

let offSocket: (() => void) | null = null

export const usePulseStore = defineStore('pulse', {
  state: () => ({
    activePulse: null as PulseNarration | null,
    history: [] as PulseNarration[],
    unreadCount: 0,
    connected: false,
  }),
  actions: {
    connect() {
      if (this.connected) return
      offSocket = onAlertMessage((msg: any) => {
        if (msg?.type === 'pulse') {
          this.receivePulse(msg.data || {})
        }
      })
      this.connected = true
    },
    disconnect() {
      if (offSocket) offSocket()
      offSocket = null
      this.connected = false
    },
    reportViewerContext(route: string, patientId?: string | null, extra?: Record<string, any>) {
      this.connect()
      sendAlertSocketMessage({
        type: 'viewer_context',
        route,
        patient_id: patientId || null,
        ...(extra || {}),
      })
    },
    receivePulse(payload: PulseNarration) {
      if (!payload?.candidate_id) return
      const cutoff = Date.now() - 24 * 60 * 60 * 1000
      this.history = [payload, ...this.history.filter(item => item.candidate_id !== payload.candidate_id)]
        .filter(item => new Date(item.occurred_at || Date.now()).getTime() >= cutoff)
        .slice(0, 80)
      if (this.activePulse) {
        this.unreadCount += 1
      }
      this.activePulse = payload
    },
    dismiss(candidateId: string) {
      sendAlertSocketMessage({ type: 'pulse_dismiss', candidate_id: candidateId })
      if (this.activePulse?.candidate_id === candidateId) {
        this.activePulse = null
      }
    },
    click(candidateId: string) {
      sendAlertSocketMessage({ type: 'pulse_click', candidate_id: candidateId })
      this.unreadCount = Math.max(0, this.unreadCount - 1)
    },
    markHistoryRead() {
      this.unreadCount = 0
    },
  },
})
