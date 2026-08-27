<template>
  <div class="ai-consult">
    <!-- 页头：标题 + 患者选择 + 更多菜单 -->
    <PageHeader title="AI 问诊" subtitle="我正在围绕哪个患者解决什么问题？">
      <template #actions>
        <a-select
          v-model:value="selectedPatientIds"
          mode="multiple"
          allow-clear
          show-search
          option-filter-prop="label"
          placeholder="选择患者"
          :options="patientOptions"
          :loading="patientsLoading"
          class="patient-select"
          @change="onPatientChange"
        />
        <MoreMenu>
          <a-menu-item @click="toggleChatMode">
            {{ chatMode === 'free' ? '切回结构化问诊' : '切到自由对话' }}
          </a-menu-item>
          <a-menu-item
            :disabled="sending || selectedPatientIds.length !== 1"
            @click="autonomousMode = !autonomousMode"
          >
            自主排查：{{ autonomousMode ? '开' : '关' }}
          </a-menu-item>
          <a-menu-item :disabled="!selectedPatientIds.length" @click="openPatientDetail">
            打开患者详情
          </a-menu-item>
          <a-menu-divider />
          <a-menu-item :disabled="messages.length <= 1" @click="exportConversation">
            导出问诊
          </a-menu-item>
          <a-menu-item :disabled="!latestAssistantMessage" @click="exportConsultSummary">
            导出会诊摘要
          </a-menu-item>
          <a-menu-item :disabled="!latestAssistantMessage" @click="exportProgressNoteTemplate">
            导出病程记录
          </a-menu-item>
          <a-menu-item :disabled="!latestAssistantMessage" @click="exportConsultDocument">
            导出会诊单
          </a-menu-item>
          <a-menu-item :disabled="!latestAssistantMessage" @click="generateDocumentDraft('handoff')">
            生成交班摘要
          </a-menu-item>
          <a-menu-item :disabled="!latestAssistantMessage" @click="generateDocumentDraft('problem')">
            生成问题清单
          </a-menu-item>
          <a-menu-divider />
          <a-menu-item danger @click="clearConversation">
            清空对话
          </a-menu-item>
        </MoreMenu>
      </template>
    </PageHeader>

    <!-- 三栏布局 -->
    <div class="ai-consult__body">
      <!-- 左栏：会话列表 -->
      <aside class="ai-consult__sidebar">
        <div class="sidebar-header">
          <span class="sidebar-title">会话</span>
          <a-button size="small" type="primary" @click="handleNewSession">新建</a-button>
        </div>
        <div class="session-list">
          <div v-if="!sessions.length" class="session-empty">
            暂无会话，点击新建开始
          </div>
          <div
            v-for="session in sessions"
            :key="session.id"
            :class="['session-item', { 'is-active': session.id === currentSessionId }]"
            @click="switchSession(session.id)"
          >
            <div class="session-item__label">{{ session.label }}</div>
            <div class="session-item__meta">
              <span class="session-item__patient">{{ session.patientLabel }}</span>
              <span class="session-item__time">{{ formatRelativeTime(session.updatedAt) }}</span>
            </div>
            <button
              class="session-item__delete"
              title="删除会话"
              @click.stop="deleteSession(session.id)"
            >
              ×
            </button>
          </div>
        </div>
      </aside>

      <!-- 中栏：对话区 -->
      <main class="ai-consult__chat">
        <!-- 消息列表 -->
        <div ref="messageListRef" class="chat-messages">
          <!-- 自主排查轨迹 -->
          <div v-if="autonomousEvents.length" class="autonomous-trace">
            <div class="autonomous-trace__title">自主排查</div>
            <div
              v-for="(event, idx) in autonomousEvents.slice(-5)"
              :key="`${event.event}-${idx}`"
              class="autonomous-trace__row"
            >
              <strong>{{ event.event }}</strong>
              <span>{{ event.summary }}</span>
            </div>
          </div>

          <template v-for="item in messages" :key="item.id">
            <!-- 用户消息 -->
            <div v-if="item.role === 'user'" class="chat-row is-user">
              <div class="chat-bubble is-user">{{ item.content }}</div>
            </div>

            <!-- AI 消息：结构化折叠 -->
            <div v-else class="chat-row is-assistant">
              <div class="chat-bubble is-assistant">
                <!-- 意图标签 -->
                <div v-if="item.intentPrimary || item.messageType === 'clarification'" class="chat-intent">
                  <span
                    v-if="item.intentPrimary"
                    :class="['intent-tag', intentTagClass(item.intentFocusSection)]"
                  >
                    {{ intentTagLabel(item.intentPrimary, item.intentFocusSection) }}
                  </span>
                  <span v-if="item.messageType === 'clarification'" class="intent-tag is-clarify">
                    需补充信息
                  </span>
                </div>

                <!-- 高风险警告（简短） -->
                <div v-if="item.isHighRisk" class="high-risk-banner">
                  高风险建议，请确认后执行
                </div>

                <!-- 结构化区块：默认折叠证据和不确定性 -->
                <template v-if="item.sections?.length">
                  <div
                    v-for="(section, sIdx) in item.sections"
                    :key="`${item.id}-s-${sIdx}`"
                    :class="['section-block', sectionBlockClass(section.title)]"
                  >
                    <div
                      class="section-block__header"
                      @click="toggleSection(item.id, sIdx)"
                    >
                      <span class="section-block__title">{{ section.title }}</span>
                      <span
                        v-if="section.title === '下一步处理建议'"
                        class="section-block__count"
                      >
                        {{ section.lines.length }} 项
                      </span>
                      <svg
                        :class="['section-block__arrow', { 'is-open': !section.collapsed }]"
                        width="12" height="12" viewBox="0 0 12 12"
                      >
                        <path d="M3 4.5L6 7.5L9 4.5" stroke="currentColor" stroke-width="1.5" fill="none"/>
                      </svg>
                    </div>
                    <div v-show="!section.collapsed" class="section-block__body">
                      <div
                        v-for="(line, lIdx) in section.lines"
                        :key="`${item.id}-s-${sIdx}-l-${lIdx}`"
                        class="section-block__line"
                      >
                        <span
                          v-if="section.title === '下一步处理建议'"
                          :class="['priority-dot', priorityClass(lIdx)]"
                        >
                          {{ priorityLabel(lIdx) }}
                        </span>
                        {{ line }}
                      </div>
                    </div>
                  </div>
                </template>

                <!-- 非结构化消息：纯文本 -->
                <template v-else>
                  <div
                    v-for="(para, pIdx) in splitParagraphs(item.content)"
                    :key="`${item.id}-p-${pIdx}`"
                    class="chat-para"
                  >
                    {{ para }}
                  </div>
                </template>

                <!-- 操作栏 -->
                <div class="chat-actions">
                  <button class="chat-action-btn" @click="copyMessage(item.content)">
                    复制
                  </button>
                  <button
                    v-if="item.sections?.length"
                    class="chat-action-btn"
                    @click="expandAllSections(item.id)"
                  >
                    展开全部
                  </button>
                </div>
              </div>
            </div>
          </template>

          <!-- AI 思考中 -->
          <div v-if="sending" class="chat-row is-assistant">
            <div class="chat-bubble is-assistant is-loading">
              <a-spin size="small" />
              <span>正在生成…</span>
            </div>
          </div>

          <!-- 空状态 -->
          <div v-if="!messages.length && !sending" class="chat-empty">
            <div class="chat-empty__icon">💬</div>
            <div class="chat-empty__text">开始一次新的问诊对话</div>
          </div>
        </div>

        <!-- 快捷任务（仅 3 个） -->
        <div class="quick-tasks">
          <button
            v-for="task in quickTasks"
            :key="task.label"
            class="quick-task-btn"
            :disabled="sending"
            @click="runQuickTask(task)"
          >
            {{ task.label }}
          </button>
        </div>

        <!-- 输入区 -->
        <div class="composer">
          <textarea
            v-model.trim="draft"
            class="composer-input"
            rows="3"
            maxlength="4000"
            placeholder="输入临床问题…"
            @keydown="onComposerKeydown"
          />
          <div class="composer-footer">
            <span class="composer-hint">Enter 发送 · Shift+Enter 换行</span>
            <a-button type="primary" size="small" :loading="sending" @click="sendMessage">
              发送
            </a-button>
          </div>
        </div>
      </main>

      <!-- 右栏：患者上下文 -->
      <aside class="ai-consult__context">
        <div class="ctx-card">
          <div class="ctx-card__title">当前患者</div>
          <div class="ctx-card__body">
            <div v-if="!selectedPatientIds.length" class="ctx-empty">
              未选择患者
            </div>
            <template v-else>
              <div
                v-for="id in selectedPatientIds"
                :key="id"
                class="ctx-patient"
              >
                <span class="ctx-patient__name">
                  {{ getPatientLabel(id) }}
                </span>
                <a-button
                  v-if="selectedPatientIds.length === 1"
                  size="small"
                  type="link"
                  @click="openPatientDetail"
                >
                  详情
                </a-button>
              </div>
            </template>
          </div>
        </div>

        <div class="ctx-card">
          <div class="ctx-card__title">引用数据</div>
          <div class="ctx-card__body">
            <div v-if="!citedData.length" class="ctx-empty">
              AI 回答后将显示引用的检验、预警和用药
            </div>
            <div v-for="(item, idx) in citedData" :key="idx" class="ctx-cited">
              <span :class="['ctx-cited__tag', `is-${item.type}`]">{{ item.typeLabel }}</span>
              <span class="ctx-cited__text">{{ item.text }}</span>
            </div>
          </div>
        </div>

        <div class="ctx-card">
          <div class="ctx-card__title">数据范围</div>
          <div class="ctx-card__body">
            <div class="ctx-range">{{ dataScopeLabel }}</div>
          </div>
        </div>

        <!-- 安全提示（常驻底部） -->
        <div class="ctx-safety">
          <span class="ctx-safety__icon">⚠</span>
          <span class="ctx-safety__text">AI 回答仅供临床参考，需结合床旁评估</span>
        </div>
      </aside>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Button as AButton, Select as ASelect, Spin as ASpin, MenuItem as AMenuItem, MenuDivider as AMenuDivider, message } from 'ant-design-vue'
import { getPatients, postAiConsultChat } from '../api'
import { useAuthStore } from '../stores/auth'
import { PageHeader, MoreMenu } from '../components/common/design-system'
import { useAiConsult } from '../composables/useAiConsult'
import type { ChatMessage, ParsedSection } from '../composables/useAiConsult'

// ── 路由 & 认证 ──
const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

function pickRouteText(...values: any[]): string {
  for (const value of values) {
    if (Array.isArray(value)) {
      const hit = String(value[0] || '').trim()
      if (hit) return hit
      continue
    }
    const hit = String(value || '').trim()
    if (hit) return hit
  }
  return ''
}

const routeDeptCode = computed(() => pickRouteText(route.query.dept_code, route.query.deptCode, auth.deptCode))
const routeDeptName = computed(() => pickRouteText(route.query.dept, route.query.department))
const routePatientId = computed(() => pickRouteText(route.query.patient_id, route.query.patientId))

// ── 会话管理 ──
const {
  sessions,
  currentSessionId,
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
} = useAiConsult()

// ── 患者列表 ──
const patientsLoading = ref(false)
const patients = ref<any[]>([])
const selectedPatientIds = ref<string[]>([])

const patientOptions = computed(() =>
  patients.value.map((item: any) => ({
    value: String(item?._id || ''),
    label: `${item?.hisBed || item?.bed || '--'}床 · ${item?.name || item?.hisName || '未知'} · ${item?.clinicalDiagnosis || item?.admissionDiagnosis || '暂无诊断'}`,
  }))
)

function getPatientLabel(id: string): string {
  return patientOptions.value.find((o) => o.value === id)?.label || '未知患者'
}

const selectedPatientLabel = computed(() => {
  if (!selectedPatientIds.value.length) return '未选择患者'
  if (selectedPatientIds.value.length === 1) return getPatientLabel(selectedPatientIds.value[0] as string)
  return `${selectedPatientIds.value.length} 位患者`
})

// ── 对话状态 ──
const sending = ref(false)
const chatMode = ref<'clinical' | 'free'>('clinical')
const draft = ref('')
const messageListRef = ref<HTMLElement | null>(null)
const streamAbortController = ref<AbortController | null>(null)
const autonomousMode = ref(false)
const autonomousEvents = ref<Array<{ event: string; summary: string }>>([])

// ── 快捷任务（仅 3 个）──
const quickTasks = [
  { label: '分析当前风险', prompt: '请根据当前信息分析主要风险点，列出风险名称、一句话结论和建议动作。' },
  { label: '生成处理计划', prompt: '请根据当前信息生成处理计划，按优先级排列，标注 P1/P2/P3。' },
  { label: '生成查房摘要', prompt: '请基于当前信息生成查房摘要，按循环、呼吸、感染、肾脏、神经、营养分类。' },
]

// ── 右栏：引用数据 ──
const citedData = computed(() => {
  const latest = latestAssistantMessage.value
  if (!latest?.sections) return []
  const items: Array<{ type: string; typeLabel: string; text: string }> = []
  const examSection = latest.sections.find((s) => s.title === '建议检查')
  if (examSection) {
    examSection.lines.slice(0, 3).forEach((line) => {
      items.push({ type: 'exam', typeLabel: '检验', text: line.slice(0, 40) })
    })
  }
  const riskSection = latest.sections.find((s) => s.title === '风险点')
  if (riskSection) {
    riskSection.lines.slice(0, 2).forEach((line) => {
      items.push({ type: 'risk', typeLabel: '预警', text: line.slice(0, 40) })
    })
  }
  return items
})

const dataScopeLabel = computed(() => {
  if (!selectedPatientIds.value.length) return '通用问答，未绑定患者数据'
  const count = selectedPatientIds.value.length
  return `已绑定 ${count} 位患者，包含最近 24h 摘要、检验、预警和用药`
})

// ── 消息解析 ──
const latestAssistantMessage = computed(() => {
  return [...messages.value].reverse().find((m) => m.role === 'assistant' && m.content.trim()) || null
})

const latestUserMessage = computed(() => {
  return [...messages.value].reverse().find((m) => m.role === 'user' && m.content.trim()) || null
})

function parseStructuredSections(content: string): ParsedSection[] {
  const text = String(content || '').replace(/\r\n/g, '\n').trim()
  if (!text) return []
  const pattern = /(?:^|\n{2,})(初步判断|关键证据|风险点|不确定性|建议检查|下一步处理建议|下一步处理|安全提示)：\n([\s\S]*?)(?=\n{2,}(?:初步判断|关键证据|风险点|不确定性|建议检查|下一步处理建议|下一步处理|安全提示)：\n|$)/g
  const sections: ParsedSection[] = []
  let match: RegExpExecArray | null
  while ((match = pattern.exec(text)) !== null) {
    const title = String(match[1] || '').trim() === '下一步处理' ? '下一步处理建议' : String(match[1] || '').trim()
    const body = String(match[2] || '').trim()
    if (!title || !body) continue
    const lines = body.split('\n').map((l) => l.trim()).filter(Boolean)
    if (lines.length) {
      // 关键证据和不确定性默认折叠
      const collapseByDefault = title === '关键证据' || title === '不确定性'
      sections.push({ title, lines, collapsed: collapseByDefault })
    }
  }
  return sections
}

function sanitizeAssistantText(raw: string): string {
  let text = String(raw || '').replace(/\r\n/g, '\n').trim()
  if (!text) return ''
  text = text.replace(/<think\b[^>]*>[\s\S]*?<\/think>/gi, '')
  text = text.replace(/<think\b[^>]*>[\s\S]*$/gi, '')
  text = text.replace(/<\/?think\b[^>]*>/gi, '')
  text = text.replace(/&lt;think\b[^&]*&gt;[\s\S]*?&lt;\/think&gt;/gi, '')
  text = text.replace(/&lt;think\b[^&]*&gt;[\s\S]*$/gi, '')
  text = text.replace(/&lt;\/?think\b[^&]*&gt;/gi, '')
  const fullFence = text.match(/^\s*```(?:[\w+-]+)?\s*([\s\S]*?)\s*```\s*$/i)
  if (fullFence) text = String(fullFence[1] || '').trim()
  text = text.replace(/```(?:[\w+-]+)?\s*([\s\S]*?)```/gi, (_, inner: string) => String(inner || '').trim())
  text = text.replace(/^\s{0,3}#{1,6}\s*/gm, '')
  text = text.replace(/^\s{0,3}>\s?/gm, '')
  text = text.replace(/^\s*[-*+]\s+/gm, '')
  text = text.replace(/^\s*(\d+)\.\s+/gm, '$1、')
  text = text.replace(/\*\*([^*\n]+)\*\*/g, '$1')
  text = text.replace(/__([^_\n]+)__/g, '$1')
  text = text.replace(/`([^`\n]+)`/g, '$1')
  text = text.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '$1')
  text = text.replace(/^\s*[-*_]{3,}\s*$/gm, '')
  text = text.replace(/\n{3,}/g, '\n\n')
  return text.trim()
}

function splitParagraphs(content: string): string[] {
  return String(content || '').replace(/\r\n/g, '\n').split(/\n{2,}/).map((p) => p.trim()).filter(Boolean)
}

function highRiskText(content: string): boolean {
  return /剂量|停用|抢救|插管|拔管|升压药|去甲肾上腺素|抗生素更换|有创|手术|穿刺|镇静加深|机械通气参数调整/.test(String(content || ''))
}

// ── UI 辅助 ──
function intentTagLabel(primary?: string, focusSection?: string): string {
  if (focusSection === '建议检查') return '检查建议'
  if (focusSection === '下一步处理') return '下一步处理'
  if (focusSection === '风险点') return '风险识别'
  if (focusSection === '初步判断') return '诊断判断'
  return primary || '综合评估'
}

function intentTagClass(focusSection?: string): string {
  if (focusSection === '建议检查') return 'is-exam'
  if (focusSection === '下一步处理') return 'is-action'
  if (focusSection === '风险点') return 'is-risk'
  if (focusSection === '初步判断') return 'is-judge'
  return 'is-default'
}

function sectionBlockClass(title: string): string {
  if (title === '风险点') return 'is-risk'
  if (title === '下一步处理建议') return 'is-action'
  if (title === '建议检查') return 'is-exam'
  if (title === '安全提示') return 'is-safety'
  if (title === '不确定性') return 'is-uncertain'
  if (title === '关键证据') return 'is-evidence'
  return 'is-judge'
}

function priorityLabel(index: number): string {
  if (index === 0) return 'P1'
  if (index === 1) return 'P2'
  return 'P3'
}

function priorityClass(index: number): string {
  if (index === 0) return 'is-p1'
  if (index === 1) return 'is-p2'
  return 'is-p3'
}

function formatRelativeTime(ts: number): string {
  const diff = Date.now() - ts
  if (diff < 60_000) return '刚刚'
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分钟前`
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} 小时前`
  return new Date(ts).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
}

function toggleSection(messageId: string, sectionIdx: number) {
  const msg = messages.value.find((m) => m.id === messageId)
  if (msg?.sections?.[sectionIdx]) {
    msg.sections[sectionIdx].collapsed = !msg.sections[sectionIdx].collapsed
  }
}

function expandAllSections(messageId: string) {
  const msg = messages.value.find((m) => m.id === messageId)
  if (msg?.sections) {
    msg.sections.forEach((s) => { s.collapsed = false })
  }
}

// ── 操作 ──
function onPatientChange() {
  if (selectedPatientIds.value.length && currentSessionId.value) {
    const session = sessions.value.find((s) => s.id === currentSessionId.value)
    if (session) {
      session.patientId = selectedPatientIds.value[0] as string
      session.patientLabel = selectedPatientLabel.value
    }
  }
}

function handleNewSession() {
  createSession(selectedPatientIds.value[0] as string || '', selectedPatientLabel.value)
  addMessage(createMessage('assistant', buildGreeting()))
}

function runQuickTask(task: { label: string; prompt: string }) {
  if (!currentSessionId.value) {
    handleNewSession()
  }
  draft.value = task.prompt
  void sendMessage()
}

function toggleChatMode() {
  if (sending.value) return
  chatMode.value = chatMode.value === 'free' ? 'clinical' : 'free'
}

function openPatientDetail() {
  if (selectedPatientIds.value.length !== 1) return
  router.push({ path: `/patient/${selectedPatientIds.value[0]}`, query: { tab: 'ai' } })
}

function clearConversation() {
  if (!currentSessionId.value) return
  clearCurrentMessages()
  addMessage(createMessage('assistant', buildGreeting()))
}

// ── 消息构建 ──
type StreamDonePayload = {
  code?: number
  answer?: string
  message?: string
  error?: string
  intent_primary?: string
  intent_focus_section?: string
  message_type?: 'normal' | 'clarification' | 'final'
  pending_clarifications?: string[]
}

function createMessage(role: 'user' | 'assistant', content: string, extra: Partial<ChatMessage> = {}): ChatMessage {
  return {
    id: `${role}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    role,
    content,
    ts: Date.now(),
    isCollapsed: false,
    ...extra,
  }
}

function buildGreeting(): string {
  if (chatMode.value === 'free') {
    return '你好，我是自由对话模式。可直接提问，如涉及临床决策请以床旁评估为准。'
  }
  if (selectedPatientIds.value.length) {
    return `你好，当前已绑定：${selectedPatientLabel.value}。可追问病情、风险或处理建议。`
  }
  return '你好，我是 AI 问诊助手。选择患者后可获得更精准的回答。'
}

// ── 流式请求 ──
function buildApiUrl(path: string): string {
  const base = String(import.meta.env.VITE_API_BASE_URL || '').replace(/\/+$/, '')
  if (!base) return path
  return `${base}${path.startsWith('/') ? path : `/${path}`}`
}

function safeJsonParse(raw: string): any {
  try { return JSON.parse(raw) } catch { return null }
}

function buildRequestHistory() {
  const rows = messages.value.slice(-8).map((m) => ({
    role: m.role,
    content: String(m.content || '').slice(0, 320),
  }))
  const clarifications = clarificationContext.value
    .slice(-3)
    .map((item, idx) => `${idx + 1}、${item.question} 医生回答：${item.answer}`)
    .join('\n')
  if (clarifications) {
    rows.push({ role: 'assistant', content: `会话临时澄清上下文：\n${clarifications}`.slice(0, 480) })
  }
  return rows
}

async function streamConsultReply(
  payload: {
    message: string
    patient_id?: string
    patient_ids?: string[]
    dept_code?: string
    mode?: string
    history?: Array<{ role: string; content: string }>
    pending_clarifications?: string[]
  },
  options: { signal?: AbortSignal; onDelta?: (chunk: string) => void; onPreview?: (text: string) => void } = {},
): Promise<StreamDonePayload> {
  const res = await fetch(buildApiUrl('/api/ai/chat-consult/stream'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal: options.signal,
  })
  if (!res.ok) throw new Error(`请求失败（HTTP ${res.status}）`)
  if (!res.body) throw new Error('流式响应不可用')

  const reader = res.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  let donePayload: StreamDonePayload = {}

  const consumeBlock = (block: string) => {
    let eventName = 'message'
    const dataLines: string[] = []
    for (const rawLine of block.split('\n')) {
      const line = rawLine.trimEnd()
      if (!line || line.startsWith(':')) continue
      if (line.startsWith('event:')) { eventName = line.slice(6).trim() || 'message'; continue }
      if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart())
    }
    const dataRaw = dataLines.join('\n').trim()
    if (!dataRaw) return
    const parsed = safeJsonParse(dataRaw)
    if (eventName === 'delta') {
      const chunk = typeof parsed?.text === 'string' ? parsed.text : dataRaw
      if (chunk) options.onDelta?.(chunk)
    } else if (eventName === 'preview') {
      const previewText = typeof parsed?.text === 'string' ? parsed.text : dataRaw
      if (previewText) options.onPreview?.(previewText)
    } else if (eventName === 'done') {
      donePayload = parsed && typeof parsed === 'object' ? parsed as StreamDonePayload : { code: 0, answer: dataRaw }
    } else if (eventName === 'error') {
      throw new Error(String(parsed?.message || parsed?.error || dataRaw || 'AI问诊失败'))
    }
  }

  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n')
    let sep = buffer.indexOf('\n\n')
    while (sep >= 0) {
      consumeBlock(buffer.slice(0, sep))
      buffer = buffer.slice(sep + 2)
      sep = buffer.indexOf('\n\n')
    }
  }
  if (buffer.trim()) consumeBlock(buffer)
  return donePayload
}

async function streamAutonomousInvestigation(
  payload: { patient_id: string; dept_code?: string; question: string },
  options: { signal?: AbortSignal; onEvent?: (event: string, data: any) => void } = {},
): Promise<StreamDonePayload> {
  const res = await fetch(buildApiUrl('/api/ai/autonomous/investigate'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal: options.signal,
  })
  if (!res.ok || !res.body) throw new Error(`自主排查失败（HTTP ${res.status}）`)
  const reader = res.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  let finalPayload: any = {}
  const consumeBlock = (block: string) => {
    let eventName = 'message'
    const dataLines: string[] = []
    for (const rawLine of block.split('\n')) {
      const line = rawLine.trimEnd()
      if (!line || line.startsWith(':')) continue
      if (line.startsWith('event:')) { eventName = line.slice(6).trim() || 'message'; continue }
      if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart())
    }
    const parsed = safeJsonParse(dataLines.join('\n').trim()) || {}
    options.onEvent?.(eventName, parsed)
    if (eventName === 'final') finalPayload = { code: 0, answer: parsed.answer || '', message_type: 'final' }
    if (eventName === 'error' && !finalPayload.answer) finalPayload = { code: 0, answer: parsed.message || '自主排查中止', degraded: true }
  }
  while (true) {
    const { done, value } = await reader.read()
    if (value) {
      buffer += decoder.decode(value, { stream: !done })
      const blocks = buffer.split(/\n\n/)
      buffer = blocks.pop() || ''
      blocks.forEach(consumeBlock)
    }
    if (done) break
  }
  if (buffer.trim()) consumeBlock(buffer)
  return finalPayload
}

// ── 发送消息 ──
async function sendMessage() {
  const content = draft.value.trim()
  if (!content || sending.value) return
  if (!currentSessionId.value) handleNewSession()

  const requestMode = chatMode.value
  const activePending = [...pendingClarifications.value]
  const isClarificationAnswer = activePending.length > 0
  const history = buildRequestHistory()

  const userMsg = createMessage('user', content)
  addMessage(userMsg)
  draft.value = ''
  await scrollToBottom()

  const assistantMsg = createMessage('assistant', '')
  addMessage(assistantMsg)

  sending.value = true
  try {
    let streamRaw = ''
    const aborter = new AbortController()
    streamAbortController.value = aborter

    let donePayload: StreamDonePayload = {}
    try {
      if (autonomousMode.value && selectedPatientIds.value.length === 1) {
        autonomousEvents.value = []
        donePayload = await streamAutonomousInvestigation(
          { patient_id: selectedPatientIds.value[0] as string, dept_code: routeDeptCode.value || undefined, question: content },
          {
            signal: aborter.signal,
            onEvent: (event, data) => {
              const summary = event === 'step'
                ? `${data.tool || 'tool'} ${data.status || ''}`.trim()
                : event === 'tool_result'
                  ? `${data.tool || 'tool'} 返回证据`
                  : event === 'final'
                    ? '形成结论'
                    : String(data.message || event)
              autonomousEvents.value.push({ event, summary })
              if (event === 'tool_result') {
                updateLastAssistant(sanitizeAssistantText(`已调用 ${data.tool || '工具'}，正在整合证据...`))
              }
              void scrollToBottom()
            },
          },
        )
      } else {
        donePayload = await streamConsultReply(
          {
            message: content,
            patient_id: selectedPatientIds.value[0],
            patient_ids: selectedPatientIds.value,
            dept_code: routeDeptCode.value || undefined,
            mode: requestMode,
            history,
            pending_clarifications: activePending,
          },
          {
            signal: aborter.signal,
            onPreview: (text: string) => {
              if (!streamRaw.trim()) {
                updateLastAssistant(`${sanitizeAssistantText(text)}\n\n正在生成详细分析...`)
                void scrollToBottom()
              }
            },
            onDelta: (chunk: string) => {
              streamRaw += chunk
              updateLastAssistant(sanitizeAssistantText(streamRaw) || ' ')
              void scrollToBottom()
            },
          },
        )
      }
    } catch (streamError: any) {
      if (streamRaw.trim()) {
        message.warning('流式连接中断，已保留已生成内容')
      } else {
        const fallbackRes = await postAiConsultChat({
          message: content,
          patient_id: selectedPatientIds.value[0],
          patient_ids: selectedPatientIds.value,
          dept_code: routeDeptCode.value || undefined,
          mode: requestMode,
          history,
          pending_clarifications: activePending,
        })
        if (Number(fallbackRes.data?.code) !== 0) {
          throw new Error(fallbackRes.data?.message || fallbackRes.data?.error || 'AI问诊失败')
        }
        streamRaw = String(fallbackRes.data?.answer || '').trim()
        donePayload = fallbackRes.data || {}
      }
      if (!streamRaw.trim()) throw streamError
    }

    const finalAnswer = sanitizeAssistantText(String(donePayload?.answer || streamRaw || '').trim()) || '暂未生成有效回答，请稍后重试。'
    const sections = parseStructuredSections(finalAnswer)
    const msgType = donePayload?.message_type === 'clarification'
      ? 'clarification'
      : donePayload?.message_type === 'final'
        ? 'final'
        : (isClarificationAnswer ? 'final' : 'normal')

    updateLastAssistant(finalAnswer, {
      intentPrimary: String(donePayload?.intent_primary || '').trim() || undefined,
      intentFocusSection: String(donePayload?.intent_focus_section || '').trim() || undefined,
      messageType: msgType as ChatMessage['messageType'],
      sections: sections.length ? sections : undefined,
      isHighRisk: highRiskText(finalAnswer),
    })

    if (msgType === 'clarification') {
      pendingClarifications.value = Array.isArray(donePayload?.pending_clarifications)
        ? donePayload.pending_clarifications.map((item: any) => String(item || '').trim()).filter(Boolean).slice(0, 3)
        : []
    } else if (isClarificationAnswer) {
      clarificationContext.value.push(...activePending.map((q) => ({ question: q, answer: content, ts: Date.now() })))
      pendingClarifications.value = []
    }
    saveContext()
    await scrollToBottom()
  } catch (error: any) {
    const errText = error?.response?.data?.message || error?.response?.data?.error || error?.message || 'AI问诊失败'
    message.error(errText)
    updateLastAssistant(`抱歉，当前回答失败：${errText}`)
    await scrollToBottom()
  } finally {
    streamAbortController.value = null
    sending.value = false
  }
}

async function scrollToBottom() {
  await nextTick()
  const el = messageListRef.value
  if (el) el.scrollTop = el.scrollHeight
}

function onComposerKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    void sendMessage()
  }
}

async function copyMessage(content: string) {
  const text = String(content || '').trim()
  if (!text) return
  try {
    await navigator.clipboard.writeText(text)
    message.success('已复制')
  } catch {
    message.error('复制失败')
  }
}

// ── 导出功能 ──
function exportPatientPart(): string {
  if (!selectedPatientIds.value.length) return '通用问答'
  return selectedPatientLabel.value.replace(/[\\/:*?"<>|]/g, '_').slice(0, 40)
}

function downloadText(text: string, filename: string) {
  const blob = new Blob([text], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  document.body.removeChild(anchor)
  URL.revokeObjectURL(url)
}

function exportConversation() {
  try {
    const header = ['ICU AI 问诊导出', `导出时间：${new Date().toLocaleString('zh-CN')}`, `患者：${selectedPatientLabel.value}`, '']
    const rows = messages.value.map((m) => {
      const role = m.role === 'assistant' ? 'AI' : '我'
      return `[${new Date(m.ts).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}] ${role}\n${m.content}\n`
    })
    downloadText([...header, ...rows].join('\n'), `AI问诊-${exportPatientPart()}.txt`)
    message.success('已导出')
  } catch { message.error('导出失败') }
}

function findSectionLines(title: string): string[] {
  return latestAssistantMessage.value?.sections?.find((s) => s.title === title)?.lines || []
}

function exportConsultSummary() {
  try {
    const latest = latestAssistantMessage.value
    if (!latest) { message.warning('暂无可导出内容'); return }
    const sections = latest.sections || []
    const header = ['ICU AI 会诊摘要', `时间：${new Date().toLocaleString('zh-CN')}`, `患者：${selectedPatientLabel.value}`, '']
    const body = sections.flatMap((s) => [s.title, ...s.lines, ''])
    downloadText([...header, ...body].join('\n'), `AI会诊摘要-${exportPatientPart()}.txt`)
    message.success('已导出')
  } catch { message.error('导出失败') }
}

function exportProgressNoteTemplate() {
  try {
    const latest = latestAssistantMessage.value
    if (!latest) { message.warning('暂无可导出内容'); return }
    const question = String(latestUserMessage.value?.content || '').trim() || '未记录'
    const judgement = findSectionLines('初步判断')
    const risks = findSectionLines('风险点')
    const exams = findSectionLines('建议检查')
    const actions = findSectionLines('下一步处理建议')
    const rows = [
      'ICU 病程记录模板', `时间：${new Date().toLocaleString('zh-CN')}`, `患者：${selectedPatientLabel.value}`, '',
      '一、当前临床问题', question, '',
      '二、病情摘要', judgement.length ? judgement.join('\n') : latest.content.slice(0, 200), '',
      '三、主要风险点', risks.length ? risks.join('\n') : '请补充', '',
      '四、建议检查', exams.length ? exams.join('\n') : '请补充', '',
      '五、下一步处理', actions.length ? actions.map((l, i) => `${priorityLabel(i)} ${l}`).join('\n') : 'P1 请补充', '',
      '以上由 AI 生成，仅供临床参考。',
    ]
    downloadText(rows.join('\n'), `病程记录-${exportPatientPart()}.txt`)
    message.success('已导出')
  } catch { message.error('导出失败') }
}

function exportConsultDocument() {
  try {
    const latest = latestAssistantMessage.value
    if (!latest) { message.warning('暂无可导出内容'); return }
    const question = String(latestUserMessage.value?.content || '').trim() || '未记录'
    const judgement = findSectionLines('初步判断')
    const risks = findSectionLines('风险点')
    const exams = findSectionLines('建议检查')
    const actions = findSectionLines('下一步处理建议')
    const rows = [
      'ICU 会诊申请单 / 意见单', `时间：${new Date().toLocaleString('zh-CN')}`, `患者：${selectedPatientLabel.value}`, '',
      '========== 申请单 ==========', `目的：${question}`, '病情：',
      ...(judgement.length ? judgement : [latest.content.slice(0, 200)]),
      '拟请协助：', ...(risks.length ? risks : ['请补充']), '',
      '========== 意见单 ==========', '初步判断：',
      ...(judgement.length ? judgement : ['请补充']), '风险：',
      ...(risks.length ? risks : ['请补充']), '建议检查：',
      ...(exams.length ? exams : ['请补充']), '下一步：',
      ...(actions.length ? actions.map((l, i) => `${priorityLabel(i)} ${l}`) : ['P1 请补充']), '',
      '以上由 AI 生成，仅供临床参考。',
    ]
    downloadText(rows.join('\n'), `会诊单-${exportPatientPart()}.txt`)
    message.success('已导出')
  } catch { message.error('导出失败') }
}

function generateDocumentDraft(type: 'rounding' | 'handoff' | 'problem') {
  const map = {
    rounding: '请生成查房摘要，按循环、呼吸、感染、肾脏、神经、营养分类。',
    handoff: '请生成交班摘要，突出当前问题、已处理事项、待复评事项和夜间风险。',
    problem: '请生成今日问题清单和复评计划。',
  }
  draft.value = map[type]
  void sendMessage()
}

// ── 患者加载 ──
async function loadPatients() {
  patientsLoading.value = true
  try {
    const params: { dept?: string; dept_code?: string; patient_scope: 'in_dept' } = { patient_scope: 'in_dept' }
    if (routeDeptCode.value) params.dept_code = routeDeptCode.value
    else if (routeDeptName.value) params.dept = routeDeptName.value
    const res = await getPatients(params)
    let list = Array.isArray(res.data?.patients) ? res.data.patients : []
    if (!list.length && routeDeptCode.value && routeDeptName.value) {
      const fallbackRes = await getPatients({ patient_scope: 'in_dept', dept: routeDeptName.value })
      list = Array.isArray(fallbackRes.data?.patients) ? fallbackRes.data.patients : []
    }
    patients.value = list
  } catch (error: any) {
    message.error(error?.response?.data?.message || '患者列表加载失败')
  } finally {
    patientsLoading.value = false
  }
}

// ── 生命周期 ──
let saveTimer: number | null = null

onMounted(async () => {
  await loadPatients()
  const fromRoute = routePatientId.value
  if (fromRoute && patients.value.some((item: any) => String(item?._id || '') === fromRoute)) {
    selectedPatientIds.value = [fromRoute]
  }
  // Auto-select first session or create one
  if (sessions.value.length && sessions.value[0]) {
    switchSession(sessions.value[0].id)
  } else {
    handleNewSession()
  }
})

onBeforeUnmount(() => {
  if (saveTimer != null) { window.clearTimeout(saveTimer); saveTimer = null }
  if (streamAbortController.value) { streamAbortController.value.abort(); streamAbortController.value = null }
})
</script>

<style scoped>
/* ── 页面布局 ── */
.ai-consult {
  display: flex;
  flex-direction: column;
  gap: var(--section-gap, 16px);
  height: calc(100vh - 64px);
  overflow: hidden;
}

.ai-consult__body {
  display: grid;
  grid-template-columns: 240px 1fr 260px;
  gap: var(--element-gap, 12px);
  flex: 1;
  min-height: 0;
}

/* ── 患者选择 ── */
.patient-select {
  min-width: 280px;
  max-width: 400px;
}

/* ── 左栏：会话列表 ── */
.ai-consult__sidebar {
  display: flex;
  flex-direction: column;
  background: var(--color-bg-surface, #fff);
  border: 1px solid var(--color-border, #e5e6eb);
  border-radius: var(--radius-lg, 8px);
  overflow: hidden;
}

.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 12px 8px;
  border-bottom: 1px solid var(--color-border, #e5e6eb);
}

.sidebar-title {
  font-size: var(--text-body-sm, 13px);
  font-weight: 600;
  color: var(--color-text-primary, #18212b);
}

.session-list {
  flex: 1;
  overflow-y: auto;
  padding: 4px;
}

.session-empty {
  padding: 24px 12px;
  text-align: center;
  color: var(--color-text-secondary, #667085);
  font-size: var(--text-caption, 12px);
}

.session-item {
  position: relative;
  padding: 10px 12px;
  border-radius: var(--radius-md, 6px);
  cursor: pointer;
  transition: background 0.15s;
}

.session-item:hover {
  background: var(--color-bg-surface-secondary, #f7f8fa);
}

.session-item.is-active {
  background: var(--color-primary-bg, #eff6ff);
  border-left: 2px solid var(--color-primary, #2563eb);
}

.session-item__label {
  font-size: var(--text-body-sm, 13px);
  color: var(--color-text-primary, #18212b);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  padding-right: 16px;
}

.session-item__meta {
  display: flex;
  gap: 8px;
  margin-top: 2px;
  font-size: var(--text-caption, 12px);
  color: var(--color-text-secondary, #667085);
}

.session-item__patient {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 120px;
}

.session-item__time {
  white-space: nowrap;
}

.session-item__delete {
  position: absolute;
  top: 8px;
  right: 8px;
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  color: var(--color-text-secondary, #667085);
  font-size: 14px;
  cursor: pointer;
  border-radius: 4px;
  opacity: 0;
  transition: opacity 0.15s;
}

.session-item:hover .session-item__delete {
  opacity: 1;
}

.session-item__delete:hover {
  background: var(--color-danger-bg, #fef2f2);
  color: var(--color-danger, #d92d20);
}

/* ── 中栏：对话区 ── */
.ai-consult__chat {
  display: flex;
  flex-direction: column;
  background: var(--color-bg-surface, #fff);
  border: 1px solid var(--color-border, #e5e6eb);
  border-radius: var(--radius-lg, 8px);
  overflow: hidden;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* 消息行 */
.chat-row {
  display: flex;
  flex-direction: column;
  max-width: 85%;
}

.chat-row.is-user {
  align-self: flex-end;
  align-items: flex-end;
}

.chat-row.is-assistant {
  align-self: flex-start;
  align-items: flex-start;
}

.chat-bubble {
  padding: 10px 14px;
  border-radius: var(--radius-lg, 8px);
  font-size: var(--text-body, 14px);
  line-height: 1.7;
  color: var(--color-text-primary, #18212b);
  white-space: pre-wrap;
  word-break: break-word;
}

.chat-bubble.is-user {
  background: var(--color-primary, #2563eb);
  color: #fff;
  border-bottom-right-radius: 4px;
}

.chat-bubble.is-assistant {
  background: var(--color-bg-surface-secondary, #f7f8fa);
  border: 1px solid var(--color-border, #e5e6eb);
  border-bottom-left-radius: 4px;
}

.chat-bubble.is-loading {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--color-text-secondary, #667085);
}

/* 意图标签 */
.chat-intent {
  display: flex;
  gap: 6px;
  margin-bottom: 8px;
}

.intent-tag {
  display: inline-flex;
  align-items: center;
  height: 22px;
  padding: 0 8px;
  border-radius: 4px;
  font-size: var(--text-caption, 12px);
  font-weight: 600;
  border: 1px solid;
}

.intent-tag.is-judge {
  color: var(--color-primary, #2563eb);
  border-color: var(--color-primary-bg, #eff6ff);
  background: var(--color-primary-bg, #eff6ff);
}

.intent-tag.is-risk {
  color: var(--color-danger, #d92d20);
  border-color: var(--color-danger-bg, #fef2f2);
  background: var(--color-danger-bg, #fef2f2);
}

.intent-tag.is-exam {
  color: #2563eb;
  border-color: #eff6ff;
  background: #eff6ff;
}

.intent-tag.is-action {
  color: var(--color-warning, #d97706);
  border-color: var(--color-warning-bg, #fffbeb);
  background: var(--color-warning-bg, #fffbeb);
}

.intent-tag.is-clarify {
  color: var(--color-success, #059669);
  border-color: var(--color-success-bg, #ecfdf5);
  background: var(--color-success-bg, #ecfdf5);
}

/* 高风险警告 */
.high-risk-banner {
  padding: 6px 10px;
  margin-bottom: 8px;
  border-radius: 4px;
  background: var(--color-danger-bg, #fef2f2);
  color: var(--color-danger, #d92d20);
  font-size: var(--text-caption, 12px);
  font-weight: 600;
}

/* 结构化区块 */
.section-block {
  border: 1px solid var(--color-border, #e5e6eb);
  border-radius: var(--radius-md, 6px);
  margin-bottom: 8px;
  overflow: hidden;
}

.section-block__header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  background: var(--color-bg-surface-secondary, #f7f8fa);
  cursor: pointer;
  user-select: none;
}

.section-block__title {
  font-size: var(--text-body-sm, 13px);
  font-weight: 600;
  color: var(--color-text-primary, #18212b);
}

.section-block__count {
  font-size: var(--text-caption, 12px);
  color: var(--color-text-secondary, #667085);
  margin-left: auto;
  margin-right: 4px;
}

.section-block__arrow {
  color: var(--color-text-secondary, #667085);
  transition: transform 0.2s;
}

.section-block__arrow.is-open {
  transform: rotate(180deg);
}

.section-block__body {
  padding: 8px 12px;
}

.section-block__line {
  font-size: var(--text-body, 14px);
  line-height: 1.7;
  color: var(--color-text-primary, #18212b);
  padding: 2px 0;
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

/* 区块类型颜色 */
.section-block.is-risk {
  border-color: rgba(217, 45, 32, 0.2);
}
.section-block.is-risk .section-block__header {
  background: var(--color-danger-bg, #fef2f2);
}
.section-block.is-risk .section-block__title {
  color: var(--color-danger, #d92d20);
}

.section-block.is-action {
  border-color: rgba(217, 119, 6, 0.2);
}
.section-block.is-action .section-block__header {
  background: var(--color-warning-bg, #fffbeb);
}
.section-block.is-action .section-block__title {
  color: var(--color-warning, #d97706);
}

.section-block.is-exam {
  border-color: rgba(37, 99, 235, 0.2);
}
.section-block.is-exam .section-block__header {
  background: #eff6ff;
}
.section-block.is-exam .section-block__title {
  color: #2563eb;
}

.section-block.is-safety .section-block__header {
  background: var(--color-warning-bg, #fffbeb);
}
.section-block.is-safety .section-block__title {
  color: var(--color-warning, #d97706);
}

.section-block.is-evidence,
.section-block.is-uncertain {
  border-color: var(--color-border, #e5e6eb);
}

/* 优先级标记 */
.priority-dot {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 28px;
  height: 20px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 700;
  flex-shrink: 0;
}

.priority-dot.is-p1 {
  background: #dc2626;
  color: #fff;
}

.priority-dot.is-p2 {
  background: #d97706;
  color: #fff;
}

.priority-dot.is-p3 {
  background: #2563eb;
  color: #fff;
}

/* 操作栏 */
.chat-actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--color-border, #e5e6eb);
}

.chat-action-btn {
  padding: 2px 8px;
  border: 1px solid var(--color-border, #e5e6eb);
  border-radius: 4px;
  background: transparent;
  color: var(--color-text-secondary, #667085);
  font-size: var(--text-caption, 12px);
  cursor: pointer;
  transition: all 0.15s;
}

.chat-action-btn:hover {
  background: var(--color-bg-surface-secondary, #f7f8fa);
  color: var(--color-text-primary, #18212b);
}

/* 段落 */
.chat-para + .chat-para {
  margin-top: 8px;
}

/* 自主排查轨迹 */
.autonomous-trace {
  padding: 10px 12px;
  border: 1px solid rgba(5, 150, 105, 0.2);
  border-radius: var(--radius-md, 6px);
  background: var(--color-success-bg, #ecfdf5);
}

.autonomous-trace__title {
  font-size: var(--text-caption, 12px);
  font-weight: 700;
  color: var(--color-success, #059669);
  margin-bottom: 6px;
}

.autonomous-trace__row {
  display: grid;
  grid-template-columns: 72px 1fr;
  gap: 8px;
  font-size: var(--text-caption, 12px);
  color: var(--color-text-primary, #18212b);
}

.autonomous-trace__row strong {
  color: var(--color-success, #059669);
}

/* 空状态 */
.chat-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: var(--color-text-secondary, #667085);
}

.chat-empty__icon {
  font-size: 32px;
}

.chat-empty__text {
  font-size: var(--text-body, 14px);
}

/* ── 快捷任务 ── */
.quick-tasks {
  display: flex;
  gap: 8px;
  padding: 8px 16px;
  border-top: 1px solid var(--color-border, #e5e6eb);
}

.quick-task-btn {
  flex: 1;
  padding: 6px 12px;
  border: 1px solid var(--color-border, #e5e6eb);
  border-radius: var(--radius-md, 6px);
  background: transparent;
  color: var(--color-text-primary, #18212b);
  font-size: var(--text-body-sm, 13px);
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}

.quick-task-btn:hover:not(:disabled) {
  background: var(--color-primary-bg, #eff6ff);
  border-color: var(--color-primary, #2563eb);
  color: var(--color-primary, #2563eb);
}

.quick-task-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* ── 输入区 ── */
.composer {
  padding: 12px 16px;
  border-top: 1px solid var(--color-border, #e5e6eb);
}

.composer-input {
  width: 100%;
  resize: none;
  border: 1px solid var(--color-border, #e5e6eb);
  border-radius: var(--radius-md, 6px);
  padding: 10px 12px;
  font-size: var(--text-body, 14px);
  line-height: 1.6;
  color: var(--color-text-primary, #18212b);
  background: var(--color-bg-surface, #fff);
  outline: none;
  transition: border-color 0.15s;
}

.composer-input::placeholder {
  color: var(--color-text-secondary, #667085);
}

.composer-input:focus {
  border-color: var(--color-primary, #2563eb);
}

.composer-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 8px;
}

.composer-hint {
  font-size: var(--text-caption, 12px);
  color: var(--color-text-secondary, #667085);
}

/* ── 右栏：患者上下文 ── */
.ai-consult__context {
  display: flex;
  flex-direction: column;
  gap: var(--element-gap, 12px);
  overflow-y: auto;
}

.ctx-card {
  background: var(--color-bg-surface, #fff);
  border: 1px solid var(--color-border, #e5e6eb);
  border-radius: var(--radius-lg, 8px);
  overflow: hidden;
}

.ctx-card__title {
  padding: 10px 12px;
  font-size: var(--text-body-sm, 13px);
  font-weight: 600;
  color: var(--color-text-primary, #18212b);
  background: var(--color-bg-surface-secondary, #f7f8fa);
  border-bottom: 1px solid var(--color-border, #e5e6eb);
}

.ctx-card__body {
  padding: 10px 12px;
}

.ctx-empty {
  font-size: var(--text-caption, 12px);
  color: var(--color-text-secondary, #667085);
  line-height: 1.6;
}

.ctx-patient {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.ctx-patient__name {
  font-size: var(--text-body-sm, 13px);
  color: var(--color-text-primary, #18212b);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.ctx-cited {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  padding: 4px 0;
}

.ctx-cited__tag {
  display: inline-flex;
  align-items: center;
  height: 18px;
  padding: 0 6px;
  border-radius: 3px;
  font-size: 11px;
  font-weight: 600;
  flex-shrink: 0;
}

.ctx-cited__tag.is-exam {
  color: #2563eb;
  background: #eff6ff;
}

.ctx-cited__tag.is-risk {
  color: #d92d20;
  background: #fef2f2;
}

.ctx-cited__text {
  font-size: var(--text-caption, 12px);
  color: var(--color-text-primary, #18212b);
  line-height: 1.5;
}

.ctx-range {
  font-size: var(--text-caption, 12px);
  color: var(--color-text-secondary, #667085);
  line-height: 1.6;
}

/* 安全提示 */
.ctx-safety {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  padding: 10px 12px;
  background: var(--color-warning-bg, #fffbeb);
  border: 1px solid rgba(217, 119, 6, 0.2);
  border-radius: var(--radius-lg, 8px);
}

.ctx-safety__icon {
  flex-shrink: 0;
  font-size: 14px;
}

.ctx-safety__text {
  font-size: var(--text-caption, 12px);
  color: var(--color-warning, #d97706);
  line-height: 1.5;
}

/* ── 响应式 ── */
@media (max-width: 1280px) {
  .ai-consult__body {
    grid-template-columns: 200px 1fr 220px;
  }
}

@media (max-width: 1024px) {
  .ai-consult__body {
    grid-template-columns: 1fr;
    grid-template-rows: auto 1fr auto;
  }

  .ai-consult__sidebar {
    max-height: 180px;
  }

  .ai-consult__context {
    max-height: 200px;
  }

  .patient-select {
    min-width: 200px;
  }
}

@media (max-width: 640px) {
  .quick-tasks {
    flex-direction: column;
  }

  .ai-consult__body {
    grid-template-columns: 1fr;
  }

  .patient-select {
    min-width: 160px;
    max-width: 200px;
  }
}
</style>
