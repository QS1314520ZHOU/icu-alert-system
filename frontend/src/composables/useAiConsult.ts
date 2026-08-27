/**
 * AI 问诊 - 会话管理 Composable
 * 职责：会话列表 CRUD、当前会话读写、localStorage 持久化
 */
import { computed, ref } from 'vue'

export interface ConsultSession {
  id: string
  label: string
  patientId: string
  patientLabel: string
  createdAt: number
  updatedAt: number
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  ts: number
  intentPrimary?: string
  intentFocusSection?: string
  messageType?: 'normal' | 'clarification' | 'final'
  sections?: ParsedSection[]
  isHighRisk?: boolean
  isCollapsed?: boolean
}

export interface ParsedSection {
  title: string
  lines: string[]
  collapsed: boolean
}

const SESSION_LIST_KEY = 'icu-ai-consult:sessions'

function uid(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8)
}

function loadSessionList(): ConsultSession[] {
  try {
    const raw = localStorage.getItem(SESSION_LIST_KEY)
    return raw ? JSON.parse(raw) : []
  } catch {
    return []
  }
}

function saveSessionList(list: ConsultSession[]) {
  localStorage.setItem(SESSION_LIST_KEY, JSON.stringify(list))
}

function loadMessages(sessionId: string): ChatMessage[] {
  try {
    const raw = localStorage.getItem(`icu-ai-consult:msg:${sessionId}`)
    return raw ? JSON.parse(raw) : []
  } catch {
    return []
  }
}

function saveMessages(sessionId: string, messages: ChatMessage[]) {
  localStorage.setItem(`icu-ai-consult:msg:${sessionId}`, JSON.stringify(messages))
}

export function useAiConsult() {
  const sessions = ref<ConsultSession[]>(loadSessionList())
  const currentSessionId = ref<string>('')
  const messages = ref<ChatMessage[]>([])
  const pendingClarifications = ref<string[]>([])
  const clarificationContext = ref<Array<{ question: string; answer: string; ts: number }>>([])

  const currentSession = computed(() =>
    sessions.value.find((s) => s.id === currentSessionId.value) || null
  )

  function createSession(patientId: string, patientLabel: string): ConsultSession {
    const session: ConsultSession = {
      id: uid(),
      label: patientLabel || '通用问答',
      patientId,
      patientLabel,
      createdAt: Date.now(),
      updatedAt: Date.now(),
    }
    sessions.value.unshift(session)
    saveSessionList(sessions.value)
    switchSession(session.id)
    return session
  }

  function switchSession(sessionId: string) {
    if (currentSessionId.value === sessionId) return
    currentSessionId.value = sessionId
    messages.value = loadMessages(sessionId)
    pendingClarifications.value = []
    clarificationContext.value = []
    // Load session context
    try {
      const raw = sessionStorage.getItem(`icu-ai-consult:ctx:${sessionId}`)
      if (raw) {
        const data = JSON.parse(raw)
        pendingClarifications.value = data.pendingClarifications || []
        clarificationContext.value = data.clarificationContext || []
      }
    } catch { /* ignore */ }
  }

  function deleteSession(sessionId: string) {
    sessions.value = sessions.value.filter((s) => s.id !== sessionId)
    saveSessionList(sessions.value)
    localStorage.removeItem(`icu-ai-consult:msg:${sessionId}`)
    sessionStorage.removeItem(`icu-ai-consult:ctx:${sessionId}`)
    if (currentSessionId.value === sessionId) {
      currentSessionId.value = sessions.value[0]?.id || ''
      if (currentSessionId.value) {
        messages.value = loadMessages(currentSessionId.value)
      } else {
        messages.value = []
      }
    }
  }

  function addMessage(msg: ChatMessage) {
    messages.value.push(msg)
    saveMessages(currentSessionId.value, messages.value)
    // Update session timestamp
    const session = sessions.value.find((s) => s.id === currentSessionId.value)
    if (session) {
      session.updatedAt = Date.now()
      if (msg.role === 'user' && messages.value.filter((m) => m.role === 'user').length === 1) {
        session.label = msg.content.slice(0, 20) + (msg.content.length > 20 ? '...' : '')
      }
      saveSessionList(sessions.value)
    }
  }

  function updateLastAssistant(content: string, meta?: Partial<ChatMessage>) {
    const last = [...messages.value].reverse().find((m) => m.role === 'assistant')
    if (last) {
      last.content = content
      if (meta) Object.assign(last, meta)
      saveMessages(currentSessionId.value, messages.value)
    }
  }

  function clearCurrentMessages() {
    messages.value = []
    pendingClarifications.value = []
    clarificationContext.value = []
    saveMessages(currentSessionId.value, messages.value)
  }

  function saveContext() {
    sessionStorage.setItem(`icu-ai-consult:ctx:${currentSessionId.value}`, JSON.stringify({
      pendingClarifications: pendingClarifications.value,
      clarificationContext: clarificationContext.value,
    }))
  }

  return {
    sessions,
    currentSessionId,
    currentSession,
    messages,
    pendingClarifications,
    clarificationContext,
    createSession,
    switchSession,
    deleteSession,
    addMessage,
    updateLastAssistant,
    clearCurrentMessages,
    saveContext,
  }
}
