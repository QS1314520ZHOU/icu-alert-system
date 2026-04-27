<template>
  <div class="consult-page">
    <a-card :bordered="false" class="consult-hero">
      <div class="consult-hero__copy">
        <div class="consult-kicker">ICU AI Consultation</div>
        <h1>AI问诊</h1>
        <p>一个纯聊天问答的 AI 问诊框。可直接输入病情、化验、治疗方案或临床疑问；也可绑定某位患者，带着患者摘要继续追问。</p>
        <div class="consult-badges">
          <span class="consult-badge">{{ sending ? 'AI 正在回答' : '对话就绪' }}</span>
          <span class="consult-badge consult-badge--soft">{{ selectedPatientLabel }}</span>
          <span class="consult-badge consult-badge--warn">仅供临床参考，需结合床旁评估</span>
        </div>
      </div>
      <div class="consult-hero__tools">
        <div class="field-label">绑定患者（可选）</div>
        <a-select
          v-model:value="selectedPatientId"
          allow-clear
          show-search
          option-filter-prop="label"
          placeholder="不选则为通用问答"
          :options="patientOptions"
          :loading="patientsLoading"
          class="patient-select"
        />
        <div class="tool-row">
          <a-button size="small" :loading="patientsLoading" @click="loadPatients">刷新患者</a-button>
          <a-button size="small" ghost :disabled="!selectedPatientId" @click="openPatientDetail">打开患者详情</a-button>
          <a-button size="small" ghost :disabled="messages.length <= 1" @click="exportConversation">导出问诊</a-button>
          <a-button size="small" ghost :disabled="!latestAssistantMessage" @click="exportConsultSummary">导出会诊摘要</a-button>
          <a-button size="small" ghost :disabled="!latestAssistantMessage" @click="exportProgressNoteTemplate">导出病程记录</a-button>
          <a-button size="small" ghost :disabled="!latestAssistantMessage" @click="exportConsultDocument">导出会诊单</a-button>
          <a-button size="small" danger ghost @click="clearConversation">清空对话</a-button>
        </div>
      </div>
    </a-card>

    <section class="consult-layout">
      <aside class="consult-side">
        <a-card :bordered="false" class="consult-panel">
          <template #title>快捷提问</template>
          <div class="prompt-list">
            <button
              v-for="prompt in quickPrompts"
              :key="prompt"
              type="button"
              class="prompt-chip"
              @click="usePrompt(prompt)"
            >
              {{ prompt }}
            </button>
          </div>
        </a-card>

        <a-card :bordered="false" class="consult-panel">
          <template #title>使用建议</template>
          <ul class="tip-list">
            <li>可以连续追问，系统会保留最近对话上下文。</li>
            <li>选中患者后，AI 会自动带入患者标签与最近预警。</li>
            <li>描述越具体，回答越有针对性，例如：指标变化、治疗时序、当前顾虑。</li>
          </ul>
        </a-card>
      </aside>

      <a-card :bordered="false" class="consult-chat">
        <template #title>
          <div class="chat-title-row">
            <span>AI 对话问答</span>
            <small>{{ selectedPatientLabel }}</small>
          </div>
        </template>

        <div ref="messageListRef" class="chat-list">
          <div
            v-for="item in messages"
            :key="item.id"
            :class="['chat-row', `is-${item.role}`]"
          >
            <div class="chat-meta">
              <div class="chat-meta__main">
                <span class="chat-role">{{ item.role === 'assistant' ? 'AI问诊助手' : '我' }}</span>
                <span class="chat-time">{{ formatTime(item.ts) }}</span>
                <span
                  v-if="item.role === 'assistant' && item.intentPrimary"
                  :class="['chat-intent-badge', intentBadgeClass(item.intentFocusSection)]"
                >
                  {{ intentBadgeLabel(item.intentPrimary, item.intentFocusSection) }}
                </span>
              </div>
              <a-button
                v-if="item.role === 'assistant' && item.content"
                size="small"
                ghost
                class="chat-copy-btn"
                @click="copyMessage(item.content)"
              >
                复制
              </a-button>
            </div>
            <template v-if="item.role === 'assistant' && parseStructuredSections(item.content).length">
              <div class="chat-bubble chat-bubble--structured">
                <div
                  v-for="(section, idx) in parseStructuredSections(item.content)"
                  :key="`${item.id}-section-${idx}`"
                  :class="['consult-section', sectionToneClass(section.title)]"
                >
                  <div class="consult-section__title">{{ section.title }}</div>
                  <div class="consult-section__body">
                    <div
                      v-for="(line, lineIdx) in section.lines"
                      :key="`${item.id}-section-${idx}-line-${lineIdx}`"
                      :class="['consult-section__line', lineToneClass(section.title)]"
                    >
                      <span
                        v-if="section.title === '下一步处理'"
                        :class="['priority-badge', priorityBadgeClass(lineIdx)]"
                      >
                        {{ priorityBadgeLabel(lineIdx) }}
                      </span>
                      {{ line }}
                    </div>
                  </div>
                </div>
              </div>
            </template>
            <div v-else class="chat-bubble">
              <template v-for="(paragraph, idx) in splitMessageParagraphs(item.content)" :key="`${item.id}-${idx}`">
                <div class="chat-bubble__paragraph">{{ paragraph }}</div>
              </template>
            </div>
          </div>

          <div v-if="sending" class="chat-row is-assistant">
            <div class="chat-meta">
              <span class="chat-role">AI问诊助手</span>
              <span class="chat-time">思考中</span>
            </div>
            <div class="chat-bubble chat-bubble--loading">
              <a-spin size="small" />
              <span>正在生成回答，请稍候…</span>
            </div>
          </div>

          <a-empty v-if="!messages.length && !sending" description="开始一次新的 AI 问诊对话" />
        </div>

        <div class="composer">
          <textarea
            v-model.trim="draft"
            class="composer-input"
            rows="4"
            maxlength="4000"
            placeholder="请输入你的问题，例如：患者乳酸持续升高、去甲肾上腺素增加到 0.2 μg/kg/min，下一步我该重点排查什么？"
            @keydown="onComposerKeydown"
          />
          <div class="composer-actions">
            <span class="composer-hint">Enter 发送，Shift + Enter 换行</span>
            <a-button type="primary" :loading="sending" @click="sendMessage">发送</a-button>
          </div>
        </div>
      </a-card>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Button as AButton, Card as ACard, Empty as AEmpty, Select as ASelect, Spin as ASpin, message } from 'ant-design-vue'
import { getPatients, postAiConsultChat } from '../api'

type ChatRole = 'user' | 'assistant'

type ChatMessage = {
  id: string
  role: ChatRole
  content: string
  ts: number
  intentPrimary?: string
  intentFocusSection?: string
}

type StructuredSection = {
  title: string
  lines: string[]
}

const router = useRouter()
const route = useRoute()
const patientsLoading = ref(false)
const sending = ref(false)
const selectedPatientId = ref<string | undefined>(undefined)
const patients = ref<any[]>([])
const draft = ref('')
const messages = ref<ChatMessage[]>([])
const messageListRef = ref<HTMLElement | null>(null)
const streamAbortController = ref<AbortController | null>(null)
let saveTimer: number | null = null

const quickPrompts = [
  '请根据当前信息给我一个初步判断和前三个风险点。',
  '如果我要进一步明确诊断，还建议补哪些检查？',
  '请帮我梳理接下来 6 小时的观察重点和处理优先级。',
  '当前治疗方案里有哪些高风险点需要立刻警惕？',
]

const patientOptions = computed(() =>
  patients.value.map((item: any) => ({
    value: String(item?._id || ''),
    label: `${item?.hisBed || item?.bed || '--'}床 · ${item?.name || item?.hisName || '未知患者'} · ${item?.clinicalDiagnosis || item?.admissionDiagnosis || '暂无诊断'}`,
  }))
)

const selectedPatientLabel = computed(() => {
  const target = patientOptions.value.find((item) => item.value === selectedPatientId.value)
  return target?.label || '未绑定具体患者'
})

const latestAssistantMessage = computed(() => {
  const rows = [...messages.value].reverse()
  return rows.find((item) => item.role === 'assistant' && String(item.content || '').trim()) || null
})

const latestUserMessage = computed(() => {
  const rows = [...messages.value].reverse()
  return rows.find((item) => item.role === 'user' && String(item.content || '').trim()) || null
})

const latestAssistantSections = computed(() => parseStructuredSections(latestAssistantMessage.value?.content || ''))

const storageKey = computed(() => `icu-ai-consult:${selectedPatientId.value || 'global'}`)

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

const routeDeptCode = computed(() => pickRouteText(route.query.dept_code, route.query.deptCode))
const routeDeptName = computed(() => pickRouteText(route.query.dept, route.query.department))
const routePatientId = computed(() => pickRouteText(route.query.patient_id, route.query.patientId))

function createMessage(role: ChatRole, content: string, extra: Partial<ChatMessage> = {}): ChatMessage {
  return {
    id: `${role}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    role,
    content,
    ts: Date.now(),
    ...extra,
  }
}

function defaultAssistantGreeting() {
  return createMessage(
    'assistant',
    selectedPatientId.value
      ? `你好，我是 AI 问诊助手。当前已绑定患者：${selectedPatientLabel.value}。你可以直接追问病情判断、风险点、检查建议或下一步处理。`
      : '你好，我是 AI 问诊助手。你可以直接输入临床问题，我会按“初步判断 / 风险提醒 / 下一步建议”的方式回答。'
  )
}

function formatTime(ts: number) {
  return new Date(ts).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

function intentBadgeLabel(primary?: string, focusSection?: string) {
  if (focusSection === '建议检查') return '检查建议'
  if (focusSection === '下一步处理') return '下一步处理'
  if (focusSection === '风险点') return '风险识别'
  if (focusSection === '初步判断') return '诊断判断'
  return primary || '综合评估'
}

function intentBadgeClass(focusSection?: string) {
  if (focusSection === '建议检查') return 'is-exam'
  if (focusSection === '下一步处理') return 'is-action'
  if (focusSection === '风险点') return 'is-risk'
  if (focusSection === '初步判断') return 'is-judgement'
  return 'is-default'
}

function sanitizeAssistantText(raw: string) {
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

function splitMessageParagraphs(content: string) {
  return String(content || '')
    .replace(/\r\n/g, '\n')
    .split(/\n{2,}/)
    .map((item) => item.trim())
    .filter(Boolean)
}

function parseStructuredSections(content: string): StructuredSection[] {
  const text = String(content || '').replace(/\r\n/g, '\n').trim()
  if (!text) return []

  const pattern = /(?:^|\n{2,})(初步判断|风险点|建议检查|下一步处理)：\n([\s\S]*?)(?=\n{2,}(?:初步判断|风险点|建议检查|下一步处理)：\n|$)/g
  const sections: StructuredSection[] = []
  let match: RegExpExecArray | null
  while ((match = pattern.exec(text)) !== null) {
    const title = String(match[1] || '').trim()
    const body = String(match[2] || '').trim()
    if (!title || !body) continue
    const lines = body
      .split('\n')
      .map((item) => item.trim())
      .filter(Boolean)
    if (lines.length) sections.push({ title, lines })
  }
  return sections
}

function sectionToneClass(title: string) {
  if (title === '风险点') return 'consult-section--risk'
  if (title === '下一步处理') return 'consult-section--action'
  if (title === '建议检查') return 'consult-section--exam'
  return 'consult-section--judgement'
}

function lineToneClass(title: string) {
  if (title === '风险点') return 'consult-section__line--risk'
  return ''
}

function priorityBadgeLabel(index: number) {
  if (index === 0) return 'P1'
  if (index === 1) return 'P2'
  return 'P3'
}

function priorityBadgeClass(index: number) {
  if (index === 0) return 'is-p1'
  if (index === 1) return 'is-p2'
  return 'is-p3'
}

async function copyMessage(content: string) {
  const text = String(content || '').trim()
  if (!text) return
  try {
    await navigator.clipboard.writeText(text)
    message.success('回答已复制')
  } catch {
    message.error('复制失败，请手动复制')
  }
}

function buildConversationExportText() {
  const header = [
    'ICU AI 问诊导出',
    `导出时间：${new Date().toLocaleString('zh-CN')}`,
    `绑定患者：${selectedPatientLabel.value}`,
    '',
  ]
  const rows = messages.value.map((item) => {
    const role = item.role === 'assistant' ? 'AI问诊助手' : '我'
    return `[${formatTime(item.ts)}] ${role}\n${String(item.content || '').trim()}\n`
  })
  return [...header, ...rows].join('\n')
}

function buildConsultSummaryExportText() {
  const latest = latestAssistantMessage.value
  if (!latest) return ''

  const sections = latestAssistantSections.value
  const latestQuestion = latestUserMessage.value
  const header = [
    'ICU AI 会诊摘要',
    `导出时间：${new Date().toLocaleString('zh-CN')}`,
    `绑定患者：${selectedPatientLabel.value}`,
    latestQuestion ? `当前问题：${String(latestQuestion.content || '').trim()}` : '当前问题：未记录',
    '',
  ]

  if (!sections.length) {
    return [...header, String(latest.content || '').trim()].join('\n')
  }

  const body = sections.flatMap((section) => {
    const title = `${section.title}`
    const rows = section.lines.map((line, idx) =>
      section.title === '下一步处理'
        ? `${priorityBadgeLabel(idx)} ${line}`
        : line
    )
    return [title, ...rows, '']
  })
  return [...header, ...body].join('\n')
}

function findSectionLines(title: string) {
  return latestAssistantSections.value.find((item) => item.title === title)?.lines || []
}

function buildProgressNoteExportText() {
  const latest = latestAssistantMessage.value
  if (!latest) return ''

  const question = String(latestUserMessage.value?.content || '').trim() || '未记录'
  const judgement = findSectionLines('初步判断')
  const risks = findSectionLines('风险点')
  const exams = findSectionLines('建议检查')
  const actions = findSectionLines('下一步处理')
  const now = new Date().toLocaleString('zh-CN')

  const rows = [
    'ICU 病程记录模板',
    `记录时间：${now}`,
    `患者：${selectedPatientLabel.value}`,
    `科室：${routeDeptName.value || routeDeptCode.value || '未提供'}`,
    '',
    '一、当前临床问题',
    question,
    '',
    '二、病情摘要',
    judgement.length ? judgement.join('\n') : String(latest.content || '').trim(),
    '',
    '三、主要风险点',
    risks.length ? risks.join('\n') : '1、请结合当前病情补充主要风险点。',
    '',
    '四、建议完善的检查/评估',
    exams.length ? exams.join('\n') : '1、请结合当前病情补充建议检查。',
    '',
    '五、下一步处理计划',
    actions.length
      ? actions.map((line, idx) => `${priorityBadgeLabel(idx)} ${line}`).join('\n')
      : 'P1 请结合当前病情补充下一步处理计划。',
    '',
    '六、备注',
    '以上内容由 AI 问诊结果整理生成，仅供临床参考，需结合床旁评估与上级医师意见。',
  ]
  return rows.join('\n')
}

function buildConsultDocumentExportText() {
  const latest = latestAssistantMessage.value
  if (!latest) return ''

  const question = String(latestUserMessage.value?.content || '').trim() || '未记录'
  const judgement = findSectionLines('初步判断')
  const risks = findSectionLines('风险点')
  const exams = findSectionLines('建议检查')
  const actions = findSectionLines('下一步处理')
  const now = new Date().toLocaleString('zh-CN')

  const rows = [
    'ICU 会诊申请单 / 会诊意见单',
    `生成时间：${now}`,
    `患者：${selectedPatientLabel.value}`,
    `申请科室：${routeDeptName.value || routeDeptCode.value || '未提供'}`,
    '',
    '========== 会诊申请单 =========＝',
    `申请目的：${question}`,
    '病情摘要：',
    ...(judgement.length ? judgement : [String(latest.content || '').trim()]),
    '拟请协助解决问题：',
    ...(risks.length ? risks : ['1、请结合当前病情明确重点风险与需协助问题。']),
    '',
    '========== 会诊意见单 =========＝',
    '初步判断：',
    ...(judgement.length ? judgement : ['1、请结合当前病情完善初步判断。']),
    '风险点：',
    ...(risks.length ? risks : ['1、请结合当前病情补充风险点。']),
    '建议检查：',
    ...(exams.length ? exams : ['1、请结合当前病情补充建议检查。']),
    '下一步处理：',
    ...(actions.length
      ? actions.map((line, idx) => `${priorityBadgeLabel(idx)} ${line}`)
      : ['P1 请结合当前病情补充下一步处理。']),
    '',
    '备注：以上内容由 AI 问诊结果整理生成，仅供临床参考，需结合床旁评估与专科医师意见。',
  ]
  return rows.join('\n')
}

function exportConversation() {
  try {
    const text = buildConversationExportText()
    const blob = new Blob([text], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    const patientPart = selectedPatientId.value
      ? String(selectedPatientLabel.value.split('·')[0] || '已绑定患者').trim()
      : '通用问答'
    const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')
    anchor.href = url
    anchor.download = `AI问诊-${patientPart}-${stamp}.txt`
    document.body.appendChild(anchor)
    anchor.click()
    document.body.removeChild(anchor)
    URL.revokeObjectURL(url)
    message.success('问诊记录已导出')
  } catch {
    message.error('导出失败，请稍后重试')
  }
}

function exportConsultSummary() {
  try {
    const text = buildConsultSummaryExportText()
    if (!text.trim()) {
      message.warning('暂无可导出的会诊摘要')
      return
    }
    const blob = new Blob([text], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    const patientPart = selectedPatientId.value
      ? String(selectedPatientLabel.value.split('·')[0] || '已绑定患者').trim()
      : '通用问答'
    const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')
    anchor.href = url
    anchor.download = `AI会诊摘要-${patientPart}-${stamp}.txt`
    document.body.appendChild(anchor)
    anchor.click()
    document.body.removeChild(anchor)
    URL.revokeObjectURL(url)
    message.success('会诊摘要已导出')
  } catch {
    message.error('导出失败，请稍后重试')
  }
}

function exportProgressNoteTemplate() {
  try {
    const text = buildProgressNoteExportText()
    if (!text.trim()) {
      message.warning('暂无可导出的病程记录模板')
      return
    }
    const blob = new Blob([text], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    const patientPart = selectedPatientId.value
      ? String(selectedPatientLabel.value.split('·')[0] || '已绑定患者').trim()
      : '通用问答'
    const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')
    anchor.href = url
    anchor.download = `病程记录模板-${patientPart}-${stamp}.txt`
    document.body.appendChild(anchor)
    anchor.click()
    document.body.removeChild(anchor)
    URL.revokeObjectURL(url)
    message.success('病程记录模板已导出')
  } catch {
    message.error('导出失败，请稍后重试')
  }
}

function exportConsultDocument() {
  try {
    const text = buildConsultDocumentExportText()
    if (!text.trim()) {
      message.warning('暂无可导出的会诊单')
      return
    }
    const blob = new Blob([text], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    const patientPart = selectedPatientId.value
      ? String(selectedPatientLabel.value.split('·')[0] || '已绑定患者').trim()
      : '通用问答'
    const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')
    anchor.href = url
    anchor.download = `会诊申请单-意见单-${patientPart}-${stamp}.txt`
    document.body.appendChild(anchor)
    anchor.click()
    document.body.removeChild(anchor)
    URL.revokeObjectURL(url)
    message.success('会诊单已导出')
  } catch {
    message.error('导出失败，请稍后重试')
  }
}

function buildApiUrl(path: string) {
  const base = String(import.meta.env.VITE_API_BASE_URL || '').replace(/\/+$/, '')
  if (!base) return path
  return `${base}${path.startsWith('/') ? path : `/${path}`}`
}

function safeJsonParse(raw: string) {
  try {
    return JSON.parse(raw)
  } catch {
    return null
  }
}

function scheduleSaveConversation(delay = 180) {
  if (saveTimer != null) window.clearTimeout(saveTimer)
  saveTimer = window.setTimeout(() => {
    saveConversation()
    saveTimer = null
  }, delay)
}

type StreamDonePayload = {
  code?: number
  answer?: string
  message?: string
  error?: string
  degraded?: boolean
  intent_primary?: string
  intent_focus_section?: string
}

async function streamConsultReply(
  payload: {
    message: string
    patient_id?: string
    history?: Array<{ role: 'user' | 'assistant'; content: string }>
  },
  options: {
    signal?: AbortSignal
    onDelta?: (chunk: string) => void
    onPreview?: (text: string) => void
  } = {},
): Promise<StreamDonePayload> {
  const res = await fetch(buildApiUrl('/api/ai/chat-consult/stream'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal: options.signal,
  })
  if (!res.ok) {
    throw new Error(`请求失败（HTTP ${res.status}）`)
  }
  if (!res.body) {
    throw new Error('流式响应不可用')
  }

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
      if (line.startsWith('event:')) {
        eventName = line.slice(6).trim() || 'message'
        continue
      }
      if (line.startsWith('data:')) {
        dataLines.push(line.slice(5).trimStart())
      }
    }
    const dataRaw = dataLines.join('\n').trim()
    if (!dataRaw) return
    const parsed = safeJsonParse(dataRaw)

    if (eventName === 'delta') {
      const chunk = typeof parsed?.text === 'string' ? parsed.text : dataRaw
      if (chunk) options.onDelta?.(chunk)
      return
    }
    if (eventName === 'preview') {
      const previewText = typeof parsed?.text === 'string' ? parsed.text : dataRaw
      if (previewText) options.onPreview?.(previewText)
      return
    }
    if (eventName === 'done') {
      if (parsed && typeof parsed === 'object') donePayload = parsed as StreamDonePayload
      else donePayload = { code: 0, answer: dataRaw }
      return
    }
    if (eventName === 'error') {
      const errText = String(parsed?.message || parsed?.error || dataRaw || 'AI问诊失败')
      throw new Error(errText)
    }
  }

  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n')
    let sep = buffer.indexOf('\n\n')
    while (sep >= 0) {
      const block = buffer.slice(0, sep)
      buffer = buffer.slice(sep + 2)
      consumeBlock(block)
      sep = buffer.indexOf('\n\n')
    }
  }
  if (buffer.trim()) consumeBlock(buffer)
  return donePayload
}

function normalizeMessages(raw: unknown): ChatMessage[] {
  if (!Array.isArray(raw)) return [defaultAssistantGreeting()]
  const rows: ChatMessage[] = raw
    .map((item: any): ChatMessage => ({
      id: String(item?.id || `${item?.role || 'assistant'}-${Math.random().toString(36).slice(2, 8)}`),
      role: item?.role === 'user' ? 'user' : 'assistant',
      content: item?.role === 'user'
        ? String(item?.content || '').trim()
        : sanitizeAssistantText(String(item?.content || '')),
      ts: Number(item?.ts || Date.now()),
      intentPrimary: item?.role === 'assistant' ? String(item?.intentPrimary || item?.intent_primary || '').trim() || undefined : undefined,
      intentFocusSection: item?.role === 'assistant' ? String(item?.intentFocusSection || item?.intent_focus_section || '').trim() || undefined : undefined,
    }))
    .filter((item: ChatMessage) => Boolean(item.content))
  return rows.length ? rows : [defaultAssistantGreeting()]
}

function saveConversation() {
  localStorage.setItem(storageKey.value, JSON.stringify(messages.value))
}

function loadConversation() {
  try {
    const raw = localStorage.getItem(storageKey.value)
    messages.value = normalizeMessages(raw ? JSON.parse(raw) : null)
  } catch {
    messages.value = [defaultAssistantGreeting()]
  }
  void scrollToBottom()
}

async function scrollToBottom() {
  await nextTick()
  const el = messageListRef.value
  if (el) {
    el.scrollTop = el.scrollHeight
  }
}

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

function usePrompt(prompt: string) {
  draft.value = prompt
}

function openPatientDetail() {
  if (!selectedPatientId.value) return
  router.push({ path: `/patient/${selectedPatientId.value}`, query: { tab: 'ai' } })
}

function clearConversation() {
  messages.value = [defaultAssistantGreeting()]
  saveConversation()
}

function onComposerKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    void sendMessage()
  }
}

async function sendMessage() {
  const content = draft.value.trim()
  if (!content || sending.value) return

  const history = messages.value.slice(-8).map((item) => ({
    role: item.role,
    content: String(item.content || '').slice(0, 320),
  }))
  const userMessage = createMessage('user', content)
  messages.value.push(userMessage)
  draft.value = ''
  saveConversation()
  await scrollToBottom()

  const assistantMessage = createMessage('assistant', '')
  messages.value.push(assistantMessage)
  scheduleSaveConversation()

  sending.value = true
  try {
    let streamRaw = ''
    const aborter = new AbortController()
    streamAbortController.value = aborter

    let donePayload: StreamDonePayload = {}
    try {
      donePayload = await streamConsultReply(
        {
          message: content,
          patient_id: selectedPatientId.value,
          history,
        },
        {
          signal: aborter.signal,
          onPreview: (text: string) => {
            if (!streamRaw.trim()) {
              assistantMessage.content = `${sanitizeAssistantText(text)}\n\n正在生成详细分析...`
              scheduleSaveConversation()
              void scrollToBottom()
            }
          },
          onDelta: (chunk: string) => {
            streamRaw += chunk
            assistantMessage.content = sanitizeAssistantText(streamRaw) || ' '
            scheduleSaveConversation()
            void scrollToBottom()
          },
        },
      )
    } catch (streamError: any) {
      if (streamRaw.trim()) {
        message.warning('流式连接中断，已保留已生成内容')
      } else {
        const fallbackRes = await postAiConsultChat({
          message: content,
          patient_id: selectedPatientId.value,
          history,
        })
        if (Number(fallbackRes.data?.code) !== 0) {
          throw new Error(fallbackRes.data?.message || fallbackRes.data?.error || 'AI问诊失败')
        }
        streamRaw = String(fallbackRes.data?.answer || '').trim()
        donePayload = fallbackRes.data || {}
      }
      if (!streamRaw.trim()) {
        throw streamError
      }
    }

    const finalAnswer = sanitizeAssistantText(String(donePayload?.answer || streamRaw || '').trim()) || '暂未生成有效回答，请稍后重试。'
    assistantMessage.content = finalAnswer
    assistantMessage.intentPrimary = String(donePayload?.intent_primary || '').trim() || undefined
    assistantMessage.intentFocusSection = String(donePayload?.intent_focus_section || '').trim() || undefined
    saveConversation()
    await scrollToBottom()
  } catch (error: any) {
    const errText = error?.response?.data?.message || error?.response?.data?.error || error?.message || 'AI问诊失败'
    message.error(errText)
    assistantMessage.content = `抱歉，当前回答失败：${errText}`
    scheduleSaveConversation()
    await scrollToBottom()
  } finally {
    streamAbortController.value = null
    sending.value = false
  }
}

watch(selectedPatientId, () => {
  loadConversation()
})

watch(messages, () => {
  scheduleSaveConversation()
}, { deep: true })

onMounted(async () => {
  await loadPatients()
  const fromRoute = routePatientId.value
  if (fromRoute && patients.value.some((item: any) => String(item?._id || '') === fromRoute)) {
    selectedPatientId.value = fromRoute
  }
  loadConversation()
})

onBeforeUnmount(() => {
  if (saveTimer != null) {
    window.clearTimeout(saveTimer)
    saveTimer = null
  }
  if (streamAbortController.value) {
    streamAbortController.value.abort()
    streamAbortController.value = null
  }
})
</script>

<style scoped>
.consult-page {
  display: grid;
  gap: 16px;
}

.consult-hero,
.consult-panel,
.consult-chat {
  border: 1px solid rgba(80, 199, 255, 0.12);
  background: linear-gradient(180deg, rgba(7, 20, 34, 0.94) 0%, rgba(4, 12, 22, 0.97) 100%);
}

.consult-hero {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(320px, 0.8fr);
  gap: 20px;
}

.consult-kicker {
  color: #67e8f9;
  font-size: 11px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

.consult-hero h1 {
  margin: 10px 0 8px;
  color: #ecfeff;
  font-size: 30px;
  line-height: 1.15;
}

.consult-hero p {
  margin: 0;
  color: #9cc2d1;
  line-height: 1.75;
}

.consult-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 14px;
}

.consult-badge {
  padding: 6px 10px;
  border-radius: 999px;
  border: 1px solid rgba(125, 211, 252, 0.16);
  background: rgba(8, 28, 44, 0.7);
  color: #e0f7ff;
  font-size: 12px;
}

.consult-badge--soft {
  color: #8fd4e6;
}

.consult-badge--warn {
  color: #fbbf24;
}

.consult-hero__tools {
  display: grid;
  gap: 10px;
  align-content: start;
}

.field-label {
  color: #8cb7c9;
  font-size: 12px;
}

.patient-select {
  width: 100%;
}

.tool-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.consult-layout {
  display: grid;
  grid-template-columns: 320px minmax(0, 1fr);
  gap: 16px;
}

.consult-side {
  display: grid;
  gap: 16px;
  align-content: start;
}

.prompt-list {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.prompt-chip {
  width: 100%;
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid rgba(125, 211, 252, 0.14);
  background: rgba(8, 28, 44, 0.72);
  color: #dffbff;
  font-size: 12px;
  text-align: left;
  cursor: pointer;
  transition: transform 0.18s ease, border-color 0.18s ease;
}

.prompt-chip:hover {
  transform: translateY(-1px);
  border-color: rgba(125, 211, 252, 0.3);
}

.tip-list {
  margin: 0;
  padding-left: 18px;
  color: #b9d6e4;
  line-height: 1.8;
}

.consult-chat {
  min-height: 72vh;
}

.chat-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.chat-title-row small {
  color: #7f97bd;
  font-size: 11px;
}

.chat-list {
  display: grid;
  gap: 14px;
  min-height: 52vh;
  max-height: 62vh;
  overflow: auto;
  padding-right: 4px;
}

.chat-row {
  display: grid;
  gap: 6px;
}

.chat-row.is-user {
  justify-items: end;
}

.chat-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.chat-row.is-user .chat-meta {
  justify-content: flex-end;
}

.chat-meta__main {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.chat-role {
  color: #8fe7ff;
  font-size: 12px;
  font-weight: 700;
}

.chat-time {
  color: #6f88aa;
  font-size: 11px;
}

.chat-intent-badge {
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  padding: 0 8px;
  border-radius: 999px;
  border: 1px solid rgba(125, 211, 252, 0.16);
  background: rgba(8, 28, 44, 0.78);
  color: #cfeeff;
  font-size: 11px;
  font-weight: 700;
  line-height: 1;
}

.chat-intent-badge.is-judgement {
  border-color: rgba(34, 211, 238, 0.2);
  color: #a5f3fc;
}

.chat-intent-badge.is-risk {
  border-color: rgba(251, 113, 133, 0.24);
  color: #fecdd3;
}

.chat-intent-badge.is-exam {
  border-color: rgba(96, 165, 250, 0.24);
  color: #bfdbfe;
}

.chat-intent-badge.is-action {
  border-color: rgba(245, 158, 11, 0.24);
  color: #fde68a;
}

.chat-bubble {
  max-width: min(820px, 100%);
  white-space: pre-wrap;
  line-height: 1.8;
  padding: 14px 16px;
  border-radius: 16px;
  border: 1px solid rgba(125, 211, 252, 0.14);
  background: rgba(8, 28, 44, 0.74);
  color: #e6f6ff;
}

.chat-bubble__paragraph + .chat-bubble__paragraph {
  margin-top: 10px;
}

.chat-copy-btn {
  flex: 0 0 auto;
}

.chat-bubble--structured {
  display: grid;
  gap: 12px;
}

.consult-section {
  border: 1px solid rgba(125, 211, 252, 0.14);
  border-radius: 14px;
  background: rgba(6, 21, 35, 0.36);
  overflow: hidden;
}

.consult-section__title {
  padding: 10px 14px;
  background: rgba(17, 79, 119, 0.18);
  color: #8fe9ff;
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.02em;
}

.consult-section__body {
  display: grid;
  gap: 8px;
  padding: 12px 14px 14px;
}

.consult-section__line {
  white-space: pre-wrap;
  line-height: 1.8;
}

.consult-section__line--risk {
  color: #ffd5d5;
}

.priority-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 34px;
  margin-right: 8px;
  padding: 1px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  line-height: 1.8;
  vertical-align: middle;
}

.priority-badge.is-p1 {
  color: #fff1f2;
  background: rgba(220, 38, 38, 0.9);
}

.priority-badge.is-p2 {
  color: #fff7ed;
  background: rgba(217, 119, 6, 0.88);
}

.priority-badge.is-p3 {
  color: #eff6ff;
  background: rgba(37, 99, 235, 0.82);
}

.consult-section--judgement .consult-section__title {
  background: rgba(17, 79, 119, 0.18);
}

.consult-section--risk {
  border-color: rgba(248, 113, 113, 0.18);
  background: rgba(60, 14, 23, 0.26);
}

.consult-section--risk .consult-section__title {
  color: #fecaca;
  background: rgba(220, 38, 38, 0.18);
}

.consult-section--action {
  border-color: rgba(250, 204, 21, 0.16);
  background: rgba(52, 34, 9, 0.24);
}

.consult-section--action .consult-section__title {
  color: #fde68a;
  background: rgba(202, 138, 4, 0.18);
}

.consult-section--exam {
  border-color: rgba(96, 165, 250, 0.18);
  background: rgba(11, 30, 56, 0.24);
}

.consult-section--exam .consult-section__title {
  color: #bfdbfe;
  background: rgba(37, 99, 235, 0.18);
}

.chat-row.is-user .chat-bubble {
  background: linear-gradient(180deg, rgba(17, 79, 119, 0.92), rgba(8, 42, 67, 0.98));
}

.chat-bubble--loading {
  display: inline-flex;
  align-items: center;
  gap: 10px;
}

.composer {
  margin-top: 16px;
  border-top: 1px solid rgba(80, 199, 255, 0.1);
  padding-top: 14px;
  display: grid;
  gap: 10px;
}

.composer-input {
  width: 100%;
  resize: vertical;
  border-radius: 14px;
  border: 1px solid rgba(125, 211, 252, 0.16);
  background: rgba(8, 20, 34, 0.94);
  color: #ecfeff;
  padding: 12px 14px;
  outline: none;
  line-height: 1.7;
}

.composer-input::placeholder {
  color: #6f88aa;
}

.composer-input:focus {
  border-color: rgba(56, 189, 248, 0.45);
  box-shadow: 0 0 0 3px rgba(14, 165, 233, 0.12);
}

.composer-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.composer-hint {
  color: #7f97bd;
  font-size: 11px;
}

html[data-theme='light'] .consult-page {
  color: #16324f;
}

html[data-theme='light'] .consult-hero,
html[data-theme='light'] .consult-panel,
html[data-theme='light'] .consult-chat,
html[data-theme='light'] .prompt-chip,
html[data-theme='light'] .chat-bubble,
html[data-theme='light'] .composer-input {
  border-color: rgba(187, 204, 220, 0.72);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.98) 0%, rgba(242, 247, 252, 0.98) 100%);
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.06);
}

html[data-theme='light'] .consult-kicker,
html[data-theme='light'] .chat-role {
  color: #1d4ed8;
}

html[data-theme='light'] .chat-intent-badge {
  background: rgba(255, 255, 255, 0.98);
  border-color: rgba(187, 204, 220, 0.72);
  color: #355a7c;
}

html[data-theme='light'] .chat-intent-badge.is-judgement {
  color: #0f766e;
  border-color: rgba(45, 212, 191, 0.28);
}

html[data-theme='light'] .chat-intent-badge.is-risk {
  color: #b91c1c;
  border-color: rgba(248, 113, 113, 0.28);
}

html[data-theme='light'] .chat-intent-badge.is-exam {
  color: #1d4ed8;
  border-color: rgba(96, 165, 250, 0.3);
}

html[data-theme='light'] .chat-intent-badge.is-action {
  color: #92400e;
  border-color: rgba(245, 158, 11, 0.3);
}

html[data-theme='light'] .consult-hero h1 {
  color: #16324f;
}

html[data-theme='light'] .consult-hero p,
html[data-theme='light'] .tip-list,
html[data-theme='light'] .chat-time,
html[data-theme='light'] .composer-hint,
html[data-theme='light'] .chat-title-row small,
html[data-theme='light'] .field-label {
  color: #6a8098;
}

html[data-theme='light'] .consult-badge {
  border-color: rgba(187, 204, 220, 0.72);
  background: #ffffff;
  color: #355a7c;
}

html[data-theme='light'] .consult-badge--warn {
  color: #b45309;
}

html[data-theme='light'] .prompt-chip {
  color: #223a54;
}

html[data-theme='light'] .chat-bubble {
  color: #223a54;
  background: #ffffff;
}

html[data-theme='light'] .consult-section {
  border-color: rgba(187, 204, 220, 0.72);
  background: rgba(248, 251, 255, 0.92);
}

html[data-theme='light'] .consult-section__title {
  color: #1d4ed8;
  background: rgba(219, 234, 254, 0.9);
}

html[data-theme='light'] .consult-section--risk {
  border-color: rgba(248, 113, 113, 0.26);
  background: rgba(254, 242, 242, 0.96);
}

html[data-theme='light'] .consult-section--risk .consult-section__title {
  color: #b91c1c;
  background: rgba(254, 226, 226, 0.96);
}

html[data-theme='light'] .consult-section__line--risk {
  color: #991b1b;
}

html[data-theme='light'] .consult-section--action {
  border-color: rgba(245, 158, 11, 0.26);
  background: rgba(255, 251, 235, 0.98);
}

html[data-theme='light'] .consult-section--action .consult-section__title {
  color: #92400e;
  background: rgba(254, 243, 199, 0.98);
}

html[data-theme='light'] .consult-section--exam {
  border-color: rgba(96, 165, 250, 0.24);
  background: rgba(239, 246, 255, 0.98);
}

html[data-theme='light'] .consult-section--exam .consult-section__title {
  color: #1d4ed8;
  background: rgba(219, 234, 254, 0.98);
}

html[data-theme='light'] .chat-row.is-user .chat-bubble {
  color: #eff6ff;
  background: linear-gradient(180deg, rgba(37, 99, 235, 0.92), rgba(29, 78, 216, 0.98));
}

html[data-theme='light'] .composer-input {
  color: #223a54;
}

html[data-theme='light'] .composer-input::placeholder {
  color: #8aa0b5;
}

@media (max-width: 1100px) {
  .consult-layout {
    grid-template-columns: 1fr;
  }

  .consult-hero {
    grid-template-columns: 1fr;
  }
}
</style>
