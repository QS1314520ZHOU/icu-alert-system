<template>
  <div class="mobile-page mobile-consult">
    <section class="mobile-card">
      <div class="mobile-section-head"><h2>AI问诊</h2><button type="button" @click="loadPatients">患者</button></div>
      <select v-model="patientId">
        <option value="">通用问答</option>
        <option v-for="patient in patients" :key="patientRouteIdOf(patient)" :value="patientRouteIdOf(patient)">
          {{ bedOf(patient) }} {{ patientNameOf(patient) }}
        </option>
      </select>
    </section>

    <section ref="listRef" class="mobile-chat-list">
      <article v-for="msg in messages" :key="msg.id" :class="['mobile-chat-msg', msg.role]">
        <div class="mobile-chat-avatar">{{ msg.role === 'assistant' ? 'AI' : '我' }}</div>
        <div class="mobile-chat-bubble">
          <div class="mobile-chat-role">{{ msg.role === 'assistant' ? '智能助手' : '我' }}</div>
          <p>{{ msg.content }}</p>
          <div v-if="msg.pending" class="mobile-typing" aria-label="AI正在生成">
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
import { getPatients, postAiConsultChat } from '../api'
import { useMobileShell } from '../composables/useMobileShell'
import { arrayFromResponse, bedOf, patientNameOf, patientRouteIdOf } from './mobileData'

const shell = useMobileShell()
const patients = ref<any[]>([])
const patientId = ref('')
const draft = ref('')
const sending = ref(false)
const listRef = ref<HTMLElement | null>(null)
const activeRequestId = ref('')
let progressTimer: number | undefined
const messages = ref<Array<{ id: string; role: 'user' | 'assistant'; content: string; pending?: boolean }>>([
  { id: 'welcome', role: 'assistant', content: '可以直接提问，也可以先选择患者后询问病情、告警、查房或治疗方案。' },
])
const quickPrompts = computed(() => patientId.value
  ? ['总结病情', '解释告警', '查房要点', '下一步处置']
  : ['问诊思路', '护理重点', '风险判断', '用药注意']
)
const progressTexts = [
  '正在读取患者上下文...',
  '正在梳理告警和关键指标...',
  '正在生成可执行建议...',
  '快好了，正在压缩成移动端易读摘要...',
]

async function loadPatients() {
  const params: Record<string, any> = { patient_scope: 'in_dept' }
  if (shell.deptCode.value) params.dept_code = shell.deptCode.value
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
  messages.value.push({ id: pendingId, role: 'assistant', content: progressTexts[0] || 'AI正在生成...', pending: true })
  sending.value = true
  startProgress(pendingId)
  await nextTick(scrollBottom)
  try {
    const history = messages.value
      .filter((item) => item.id !== 'welcome' && !item.pending)
      .slice(-8)
      .map(({ role, content }) => ({ role, content }))
    const res = await postAiConsultChat({
      message: content,
      patient_id: patientId.value || undefined,
      patient_ids: patientId.value ? [patientId.value] : undefined,
      mode: patientId.value ? 'clinical' : 'free',
      history,
    })
    if (activeRequestId.value !== requestId) return
    const answer = String(res.data?.answer || res.data?.content || res.data?.message || 'AI暂未返回有效内容。')
    replacePending(pendingId, answer)
  } catch (error: any) {
    if (activeRequestId.value !== requestId) return
    replacePending(pendingId, error?.response?.data?.detail || error?.message || '问诊请求失败。')
  } finally {
    if (activeRequestId.value === requestId) {
      sending.value = false
      activeRequestId.value = ''
    }
    stopProgress()
    await nextTick(scrollBottom)
  }
}

function startProgress(pendingId: string) {
  let index = 0
  stopProgress()
  progressTimer = window.setInterval(() => {
    index = Math.min(index + 1, progressTexts.length - 1)
    const row = messages.value.find((item) => item.id === pendingId && item.pending)
    if (row) row.content = progressTexts[index] || progressTexts[progressTexts.length - 1] || 'AI正在生成...'
    void nextTick(scrollBottom)
  }, 2200)
}

function stopProgress() {
  if (progressTimer) window.clearInterval(progressTimer)
  progressTimer = undefined
}

function replacePending(id: string, content: string) {
  const index = messages.value.findIndex((item) => item.id === id)
  if (index >= 0) messages.value[index] = { id: `a-${Date.now()}`, role: 'assistant', content }
  else messages.value.push({ id: `a-${Date.now()}`, role: 'assistant', content })
}

function stopWaiting() {
  activeRequestId.value = ''
  sending.value = false
  stopProgress()
  const pending = messages.value.find((item) => item.pending)
  if (pending) {
    pending.pending = false
    pending.content = '已停止等待。本次后台请求若稍后返回，将不会再追加到对话。'
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
