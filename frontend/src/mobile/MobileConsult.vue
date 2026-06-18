<template>
  <div class="mobile-page mobile-consult">
    <section class="mobile-card">
      <div class="mobile-section-head"><h2>辅助问诊</h2><button type="button" @click="loadPatients">患者</button></div>
      <select v-model="patientId">
        <option value="">通用问答</option>
        <option v-for="patient in patients" :key="patientRouteIdOf(patient)" :value="patientRouteIdOf(patient)">
          {{ bedOf(patient) }} {{ patientNameOf(patient) }}
        </option>
      </select>
    </section>

    <section ref="listRef" class="mobile-chat-list">
      <article v-for="msg in messages" :key="msg.id" :class="['mobile-chat-msg', msg.role]">
        <div class="mobile-chat-avatar">{{ msg.role === 'assistant' ? '辅' : '我' }}</div>
        <div class="mobile-chat-bubble">
          <div class="mobile-chat-role">{{ msg.role === 'assistant' ? '辅助问诊' : '我' }}</div>
          <p>{{ msg.content }}</p>
          <div v-if="msg.pending" class="mobile-typing" aria-label="系统正在生成">
            <i></i><i></i><i></i>
          </div>
        </div>
      </article>
    </section>

    <section class="mobile-consult-tools">
      <button v-for="item in quickPrompts" :key="item" type="button" @click="usePrompt(item)">
        {{ item }}
      </button>
    </section>

    <form class="mobile-chat-input" @submit.prevent="send">
      <textarea v-model.trim="draft" rows="2" placeholder="输入临床问题，支持绑定患者上下文"></textarea>
      <button v-if="!sending" type="submit" :disabled="!draft">发送</button>
      <button v-else type="button" @click="stopWaiting">停止</button>
    </form>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { getPatients } from '../api'
import { useMobileShell } from '../composables/useMobileShell'
import { arrayFromResponse, bedOf, patientNameOf, patientRouteIdOf } from './mobileData'

const shell = useMobileShell()
const patients = ref<any[]>([])
const patientId = ref('')
const draft = ref('')
const sending = ref(false)
const listRef = ref<HTMLElement | null>(null)
const activeRequestId = ref('')
const messages = ref<Array<{ id: string; role: 'user' | 'assistant'; content: string; pending?: boolean }>>([
  { id: 'welcome', role: 'assistant', content: '可以直接提问，也可以先选择患者后询问病情、告警、查房或治疗方案。' },
])
const quickPrompts = computed(() => patientId.value
  ? ['总结病情', '解释告警', '查房要点', '下一步处置']
  : ['问诊思路', '护理重点', '风险判断', '用药注意']
)

function buildApiUrl(path: string) {
  const base = String(import.meta.env.VITE_API_BASE_URL || '').replace(/\/+$/, '')
  return base ? `${base}${path.startsWith('/') ? path : `/${path}`}` : path
}

async function streamConsultReply(
  payload: { message: string; patient_id?: string; patient_ids?: string[]; mode?: string; history?: Array<{ role: string; content: string }> },
  onDelta: (chunk: string) => void,
): Promise<{ answer?: string; error?: string }> {
  const res = await fetch(buildApiUrl('/api/ai/chat-consult/stream'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  if (!res.body) throw new Error('流式响应不可用')
  const reader = res.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  let donePayload: any = {}
  const consumeBlock = (block: string) => {
    let event = 'message'
    const dataLines: string[] = []
    for (const raw of block.split('\n')) {
      const line = raw.trimEnd()
      if (!line || line.startsWith(':')) continue
      if (line.startsWith('event:')) { event = line.slice(6).trim() || 'message'; continue }
      if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart())
    }
    const raw = dataLines.join('\n').trim()
    if (!raw) return
    let parsed: any = null
    try { parsed = JSON.parse(raw) } catch { parsed = null }
    if (event === 'delta') { onDelta(typeof parsed?.text === 'string' ? parsed.text : raw); return }
    if (event === 'done') { donePayload = parsed || {}; return }
  }
  try {
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const parts = buffer.split('\n\n')
      buffer = parts.pop() || ''
      for (const part of parts) consumeBlock(part)
    }
    if (buffer.trim()) consumeBlock(buffer)
  } finally {
    reader.releaseLock()
  }
  return donePayload
}

async function loadPatients() {
  const params: Record<string, any> = { patient_scope: 'in_dept' }
  if (shell.deptCode.value) {
    params.dept_code = shell.deptCode.value
    params.deptCode = shell.deptCode.value
  }
  const res = await getPatients(params)
  patients.value = arrayFromResponse(res.data, ['patients'])
}

async function send() {
  const content = draft.value
  if (!content || sending.value) return
  const requestId = `r-${Date.now()}`
  const pendingId = `p-${Date.now()}`
  activeRequestId.value = requestId
  draft.value = ''
  messages.value.push({ id: `u-${Date.now()}`, role: 'user', content })
  messages.value.push({ id: pendingId, role: 'assistant', content: '', pending: true })
  sending.value = true
  await nextTick(scrollBottom)
  try {
    const history = messages.value
      .filter((item) => item.id !== 'welcome' && !item.pending)
      .slice(-8)
      .map(({ role, content }) => ({ role, content }))
    let streamStarted = false
    const done = await streamConsultReply(
      {
        message: content,
        patient_id: patientId.value || undefined,
        patient_ids: patientId.value ? [patientId.value] : undefined,
        mode: patientId.value ? 'clinical' : 'free',
        history,
      },
      (chunk: string) => {
        if (activeRequestId.value !== requestId) return
        streamStarted = true
        const row = messages.value.find((m) => m.id === pendingId)
        if (row) {
          row.content += chunk
          row.pending = true
        }
        void nextTick(scrollBottom)
      },
    )
    if (activeRequestId.value !== requestId) return
    const row = messages.value.find((m) => m.id === pendingId)
    if (row) {
      row.pending = false
      if (!streamStarted) {
        row.content = String(done?.answer || done?.message || '系统暂未返回有效内容。')
      }
    }
  } catch (error: any) {
    if (activeRequestId.value !== requestId) return
    replacePending(pendingId, error?.message || '问诊请求失败。')
  } finally {
    if (activeRequestId.value === requestId) {
      sending.value = false
      activeRequestId.value = ''
    }
    await nextTick(scrollBottom)
  }
}

function replacePending(id: string, content: string) {
  const index = messages.value.findIndex((item) => item.id === id)
  if (index >= 0) messages.value[index] = { id: `a-${Date.now()}`, role: 'assistant', content }
  else messages.value.push({ id: `a-${Date.now()}`, role: 'assistant', content })
}

function stopWaiting() {
  activeRequestId.value = ''
  sending.value = false
  const pending = messages.value.find((item) => item.pending)
  if (pending) {
    pending.pending = false
    if (!pending.content) pending.content = '已停止等待。'
  }
}

function usePrompt(text: string) {
  draft.value = patientId.value ? text : `请说明${text}`
}

function scrollBottom() {
  if (listRef.value) listRef.value.scrollTop = listRef.value.scrollHeight
}

onMounted(() => {
  void shell.resolveIdentity().finally(() => loadPatients())
})
</script>
