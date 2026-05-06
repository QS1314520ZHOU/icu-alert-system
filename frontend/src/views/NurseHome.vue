<template>
  <section class="nurse-home">
    <header class="nurse-top">
      <div>
        <strong>{{ accountName }}</strong>
        <span>{{ shiftText }} · 我的床位：{{ bedText }}</span>
      </div>
      <div class="workload">
        <span>工作负荷 {{ workload.used_minutes || 0 }} / {{ workload.estimated_minutes || 0 }} 分钟</span>
        <i><b :style="{ width: `${workload.percent || 0}%` }"></b></i>
      </div>
      <button type="button" @click="load">刷新</button>
    </header>

    <div v-if="loading" class="empty">正在生成本班时间轴和护理闭环任务...</div>
    <div v-else-if="error" class="empty danger">{{ error }}</div>

    <template v-else>
      <main v-if="isHeadMode" class="head-layout">
        <section class="panel">
          <div class="panel-head"><strong>全科床位</strong><span>{{ headBeds.length }} 床</span></div>
          <div class="bed-cloud"><span v-for="b in headBeds" :key="b.patient_id">{{ b.bed || '--' }}床 {{ b.name }}</span></div>
        </section>
        <section class="panel">
          <div class="panel-head"><strong>工作负荷热力图</strong><span>本班护理记录密度</span></div>
          <div class="heatmap"><span v-for="row in heatmap" :key="row.nurse" :class="`density-${row.tone}`">{{ row.nurse }} · {{ row.task_density }}</span></div>
        </section>
      </main>

      <main v-else class="nurse-grid">
        <section class="panel timeline-panel">
          <div class="panel-head"><strong>今日时间轴</strong><span>5 分钟格 · 点击任务处理</span></div>
          <div class="timeline">
            <div class="time-head">
              <span>床位</span>
              <span v-for="tick in ticks" :key="tick">{{ tick }}</span>
            </div>
            <div v-for="bed in beds" :key="bed.patient_id" class="bed-line">
              <strong>{{ bed.bed || '--' }}床</strong>
              <div class="task-strip">
                <button v-for="task in tasksByBed(bed.patient_id)" :key="task.task_id" type="button" :class="`task-card is-${task.status}`" @click="selectTask(task)">
                  {{ task.title }}
                </button>
              </div>
            </div>
            <div v-if="!beds.length" class="empty small">本班还没有由第一条护理记录反推到你的分管床，前端显示待接班。</div>
          </div>
        </section>

        <aside class="side">
          <section class="panel">
            <div class="panel-head"><strong>安全清单</strong><span>红黄绿闭环</span></div>
            <article v-for="item in bundles" :key="item.code" :class="`bundle is-${item.tone}`">
              <strong>{{ item.name }}</strong>
              <span>{{ item.completed }}/{{ item.total }}</span>
            </article>
          </section>
          <section class="panel">
            <div class="panel-head"><strong>与我相关的 AI 提醒</strong><span>护理执行相关</span></div>
            <article v-for="item in reminders" :key="item._id || item.created_at" class="reminder">
              <strong>{{ shortText(item.name || item.alert_type || item.rule_id) }}</strong>
              <div>
                <button type="button">已处理</button>
                <button type="button">转给医生</button>
                <button type="button">不是问题</button>
              </div>
            </article>
            <div v-if="!reminders.length" class="empty small">暂无护理执行相关 AI 提醒。</div>
          </section>
        </aside>
      </main>

      <section :class="['handoff-bar', { open: handoffShouldOpen }]">
        <div>
          <strong>一键交班</strong>
          <span>下班前 1 小时自动展开，按标准交班结构生成本班交班单。</span>
        </div>
        <button type="button" :disabled="handoffLoading || !beds.length" @click="generateHandoff">{{ handoffLoading ? '生成中' : '生成本班交班单' }}</button>
      </section>

      <div v-if="selectedTask" class="modal-mask" @click.self="selectedTask = null">
        <div class="task-modal">
          <strong>{{ selectedTask.title }}</strong>
          <p>{{ selectedTask.bed }}床 {{ selectedTask.patient_name }} · {{ fmt(selectedTask.due_at) }}</p>
          <div class="modal-actions">
            <button type="button" @click="executeTask('executed')">执行</button>
            <button type="button" @click="executeTask('delay_15m')">推迟15分钟</button>
            <button type="button" @click="executeTask('handover')">转交</button>
            <button type="button" @click="executeTask('not_applicable')">不适用</button>
          </div>
        </div>
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getNurseHome, postNurseHandoffGenerate, postNurseTaskExecute } from '../api'
import { getOperatorIdentity } from '../utils/operatorIdentity'

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const error = ref('')
const home = ref<any>(null)
const selectedTask = ref<any>(null)
const handoffLoading = ref(false)

const userId = computed(() => String(route.query.user_id || route.query.userId || route.query.userName || getOperatorIdentity() || '').trim())
const isHeadMode = computed(() => String(route.query.view || '').toLowerCase() === 'head' || ['head_nurse', 'charge_nurse'].includes(String(home.value?.account?.role || '').toLowerCase()))
const accountName = computed(() => home.value?.account?.display_name || home.value?.account?.userName || userId.value || '未识别护士')
const beds = computed(() => home.value?.beds || [])
const workload = computed(() => home.value?.workload || {})
const bundles = computed(() => home.value?.bundles || [])
const reminders = computed(() => home.value?.ai_reminders || [])
const headBeds = computed(() => home.value?.head_view?.beds || [])
const heatmap = computed(() => home.value?.head_view?.workload_heatmap || [])
const shiftText = computed(() => {
  const s = home.value?.shift
  if (!s) return '班次待配置'
  return `${s.name} ${String(s.start || '').slice(11, 16)}-${String(s.end || '').slice(11, 16)}`
})
const bedText = computed(() => beds.value.length ? beds.value.map((b: any) => `${b.bed}床`).join(' / ') : '待接班')
const ticks = computed(() => {
  const start = new Date(home.value?.shift?.start || Date.now())
  return Array.from({ length: 7 }, (_, idx) => new Date(start.getTime() + idx * 60 * 60 * 1000).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }))
})
const handoffShouldOpen = computed(() => {
  const end = new Date(home.value?.shift?.end || 0).getTime()
  return end > 0 && end - Date.now() <= 60 * 60 * 1000
})

function tasksByBed(pid: string) {
  return (home.value?.timeline || []).filter((task: any) => task.patient_id === pid)
}
function fmt(value: any) {
  return value ? new Date(value).toLocaleString('zh-CN', { hour: '2-digit', minute: '2-digit' }) : '--'
}
function shortText(value: any) {
  const text = String(value || 'AI提醒')
  return text.length > 20 ? `${text.slice(0, 20)}...` : text
}
function selectTask(task: any) {
  selectedTask.value = task
}
async function executeTask(action: string) {
  if (!selectedTask.value) return
  await postNurseTaskExecute(selectedTask.value.task_id, {
    action,
    patient_id: selectedTask.value.patient_id,
    actor: userId.value,
  })
  selectedTask.value = null
  await load()
}
async function generateHandoff() {
  handoffLoading.value = true
  try {
    await postNurseHandoffGenerate({ user_id: userId.value, patient_ids: beds.value.map((b: any) => b.patient_id), shift_code: home.value?.shift?.code || 'auto' })
  } finally {
    handoffLoading.value = false
  }
}
async function load() {
  if (!userId.value) {
    error.value = '缺少 user_id，无法按本班第一条护理记录反推分管床位。'
    return
  }
  loading.value = true
  error.value = ''
  try {
    const { data } = await getNurseHome({ user_id: userId.value, shift_code: 'auto', view: String(route.query.view || '') || undefined })
    home.value = data?.data || {}
  } catch (err: any) {
    error.value = err?.message || '护士首页加载失败'
  } finally {
    loading.value = false
  }
}
onMounted(() => {
  cleanDuplicateIdentityQuery()
  void load()
})

function cleanDuplicateIdentityQuery() {
  if (route.query.userName && (route.query.user_id || route.query.userId)) {
    const query = { ...route.query }
    delete query.user_id
    delete query.userId
    router.replace({ path: route.path, query })
  }
}
</script>

<style scoped>
.nurse-home { padding: 12px; display: grid; gap: 12px; }
.nurse-top { min-height: 80px; display: grid; grid-template-columns: minmax(0,1fr) 320px auto; align-items: center; gap: 12px; padding: 12px; border: 1px solid rgba(125,211,252,.14); border-radius: 8px; background: rgba(7,20,34,.82); }
.nurse-top strong { color: #f8fbff; font-size: 20px; }
.nurse-top span, .panel-head span, .empty, .bundle span, .task-modal p { color: #91adbd; font-size: 12px; }
.workload { display: grid; gap: 6px; }
.workload i { height: 8px; border-radius: 999px; background: rgba(148,163,184,.25); overflow: hidden; }
.workload b { display: block; height: 100%; background: #38bdf8; }
button { min-height: 44px; border: 1px solid rgba(125,211,252,.22); border-radius: 8px; background: rgba(13,44,66,.78); color: #eafcff; padding: 0 10px; cursor: pointer; }
.nurse-grid { min-height: 560px; display: grid; grid-template-columns: minmax(0, 3fr) minmax(340px, 2fr); gap: 12px; }
.side, .head-layout { display: grid; gap: 12px; }
.head-layout { grid-template-columns: 1fr 1fr; }
.panel { min-width: 0; display: grid; align-content: start; gap: 10px; padding: 12px; border: 1px solid rgba(125,211,252,.14); border-radius: 8px; background: rgba(6,18,31,.74); }
.panel-head { display: flex; justify-content: space-between; gap: 10px; }
.panel-head strong { color: #f4fbff; }
.timeline { overflow: auto; display: grid; gap: 8px; }
.time-head { min-width: 760px; display: grid; grid-template-columns: 84px repeat(7, 1fr); color: #8caabd; font-size: 12px; }
.bed-line { min-width: 760px; display: grid; grid-template-columns: 84px minmax(0,1fr); align-items: stretch; gap: 8px; }
.bed-line > strong { display: grid; place-items: center; color: #f8fbff; border-radius: 8px; background: rgba(11,33,50,.72); }
.task-strip { min-height: 58px; display: flex; align-items: center; gap: 8px; padding: 7px; border-radius: 8px; background: rgba(11,33,50,.48); overflow-x: auto; }
.task-card { flex: 0 0 132px; font-size: 12px; }
.is-future { opacity: .7; }
.is-soon { border-color: rgba(56,189,248,.55); }
.is-due { border-color: rgba(245,158,11,.65); }
.is-overdue { border-color: rgba(239,68,68,.7); color: #fecaca; }
.is-done { border-color: rgba(52,211,153,.55); color: #bbf7d0; }
.bundle, .reminder { display: flex; justify-content: space-between; gap: 10px; align-items: center; padding: 10px; border-radius: 8px; background: rgba(11,33,50,.72); }
.bundle strong, .reminder strong { color: #edf8ff; font-size: 13px; }
.bundle.is-green { border-left: 3px solid #34d399; }
.bundle.is-yellow { border-left: 3px solid #f59e0b; }
.bundle.is-red { border-left: 3px solid #ef4444; }
.reminder { display: grid; }
.reminder div { display: flex; gap: 8px; flex-wrap: wrap; }
.reminder button { min-height: 36px; }
.handoff-bar { display: flex; justify-content: space-between; gap: 12px; align-items: center; padding: 12px; border: 1px solid rgba(125,211,252,.14); border-radius: 8px; background: rgba(6,18,31,.74); opacity: .82; }
.handoff-bar.open { border-color: rgba(245,158,11,.42); opacity: 1; }
.handoff-bar strong { color: #f8fbff; display: block; }
.handoff-bar span { color: #91adbd; font-size: 12px; }
.empty { padding: 14px; border-radius: 8px; background: rgba(11,33,50,.58); }
.empty.small { padding: 10px; }
.danger { color: #fecaca; }
.modal-mask { position: fixed; inset: 0; z-index: 200; display: grid; place-items: center; background: rgba(0,0,0,.52); }
.task-modal { width: min(520px, calc(100vw - 24px)); display: grid; gap: 12px; padding: 16px; border-radius: 8px; border: 1px solid rgba(125,211,252,.22); background: #081827; }
.task-modal strong { color: #fff; font-size: 18px; }
.modal-actions { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 8px; }
.bed-cloud, .heatmap { display: flex; flex-wrap: wrap; gap: 8px; }
.bed-cloud span, .heatmap span { padding: 8px 10px; border-radius: 8px; background: rgba(11,33,50,.72); color: #eafcff; }
.density-high { border: 1px solid rgba(239,68,68,.6); }
.density-medium { border: 1px solid rgba(245,158,11,.55); }
.density-low { border: 1px solid rgba(52,211,153,.45); }
@media (max-width: 1024px) { .nurse-top, .nurse-grid, .head-layout { grid-template-columns: 1fr; } .side { grid-template-columns: 1fr 1fr; } }
@media (max-width: 760px) { .side, .handoff-bar { grid-template-columns: 1fr; flex-direction: column; align-items: stretch; } }
</style>
