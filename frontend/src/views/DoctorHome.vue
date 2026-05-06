<template>
  <section class="role-home doctor-home">
    <header class="home-top">
      <div>
        <span>主管医生首页</span>
        <strong>{{ accountName }}</strong>
      </div>
      <div class="top-meta">
        <span>{{ home?.account?.dept || '科室待识别' }}</span>
        <span>{{ shiftText }}</span>
        <span>{{ clock }}</span>
        <button type="button" @click="load">刷新</button>
      </div>
    </header>

    <div v-if="loading" class="empty">正在汇总我管的床、昨夜 AI 监控和待办...</div>
    <div v-else-if="error" class="empty danger">{{ error }}</div>
    <main v-else class="doctor-grid">
      <section class="panel focus-panel">
        <div class="panel-head">
          <strong>我的今日重点</strong>
          <span>按综合风险推理排序</span>
        </div>
        <article v-for="item in focusPatients" :key="item.patient_id" class="focus-row" @click="goPatient(item.patient_id)">
          <i :class="`tone-${tone(item.risk_level)}`"></i>
          <div>
            <strong>{{ item.bed || '--' }}床 {{ item.name || '未知患者' }}</strong>
            <span>{{ cleanReason(item.reason) }}</span>
          </div>
          <b>{{ item.risk_score || 0 }}</b>
        </article>
        <div v-if="!focusPatients.length" class="empty small">暂无重点关注患者。</div>
      </section>

      <section class="panel">
        <div class="panel-head">
          <strong>AI 昨夜替我做了什么</strong>
          <span>过去 12 小时</span>
        </div>
        <div class="kpi-grid">
          <div v-for="item in aiStats" :key="item.label" class="kpi">
            <span>{{ item.label }}</span>
            <strong>{{ item.value }}</strong>
          </div>
        </div>
        <button class="full-btn" type="button" @click="$router.push({ path: '/clinical-workflow', query: route.query })">查看夜班完整工作日志</button>
      </section>

      <section class="panel">
        <div class="panel-head">
          <strong>我的待办</strong>
          <span>未签 / 未关闭 / 未确认</span>
        </div>
        <div class="task-list">
          <article v-for="item in pendingTasks" :key="item.task_id || item.title" class="task-row">
            <strong>{{ item.title || item.detail || '临床任务' }}</strong>
            <span>{{ item.bed_label || item.bed || '--' }}床 · {{ item.module_label || item.module || '临床' }}</span>
          </article>
          <div v-if="!pendingTasks.length" class="empty small">暂无待办，仍建议复核高风险患者详情。</div>
        </div>
      </section>

      <section class="panel">
        <div class="panel-head">
          <strong>科室质控速览</strong>
          <span>当日维度</span>
        </div>
        <div class="lights">
          <button v-for="item in qualityLights" :key="item.key" type="button" :class="`light is-${item.tone}`" @click="$router.push('/analytics')">
            <span>{{ item.label }}</span>
            <b>{{ item.value }}</b>
          </button>
        </div>
      </section>
    </main>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getDoctorHome } from '../api'
import { useAuthStore } from '../stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const loading = ref(false)
const error = ref('')
const home = ref<any>(null)
const clock = ref('')
let timer: any

const userId = computed(() => String(auth.effectiveUserId || '').trim())
const accountName = computed(() => home.value?.account?.display_name || home.value?.account?.userName || userId.value || '未识别医生')
const focusPatients = computed(() => home.value?.focus_patients || [])
const pendingTasks = computed(() => (home.value?.pending_tasks || []).slice(0, 8))
const shiftText = computed(() => {
  const s = home.value?.shift
  if (!s) return '班次待配置'
  return `${s.name} ${String(s.start || '').slice(11, 16)}-${String(s.end || '').slice(11, 16)}`
})
const aiStats = computed(() => {
  const a = home.value?.ai_night_watch || {}
  return [
    { label: '告警总数', value: a.total_alerts ?? 0 },
    { label: '自动抑制', value: a.auto_suppressed ?? 0 },
    { label: '已推送', value: a.pushed ?? 0 },
    { label: '已处理', value: a.handled ?? 0 },
    { label: '待跟进', value: a.pending_followup ?? 0 },
    { label: '综合判断', value: a.integrated_reasoning ?? 0 },
    { label: '判断采纳', value: a.integrated_adopted ?? 0 },
    { label: '主动提醒点击', value: `${a.pulse_clicks ?? 0}/${a.pulse_pushes ?? 0}` },
  ]
})
const qualityLights = computed(() => {
  const q = home.value?.quality_summary || {}
  const rows = q?.scanner_health?.rows || q?.rows || []
  const labels = ['VAP', 'CRBSI', 'CAUTI', '拔管失败', '镇静过度', '谵妄发生率']
  return labels.map((label) => {
    const row = rows.find((r: any) => String(r?.name || r?.scanner_name || '').toLowerCase().includes(label.toLowerCase()))
    const value = row?.rate ?? row?.count ?? row?.value ?? '--'
    const num = Number(value)
    return { key: label, label, value, tone: Number.isFinite(num) && num > 0 ? 'yellow' : 'green' }
  })
})

function tone(value: string) {
  const key = String(value || '').toLowerCase()
  if (['critical', 'high'].includes(key)) return 'critical'
  if (key === 'warning') return 'warning'
  if (key === 'info') return 'info'
  return 'unknown'
}
function goPatient(id: string) {
  if (id) router.push({ path: `/patient/${id}`, query: route.query })
}
function cleanReason(value: any) {
  if (value && typeof value === 'object') {
    const summary = String(value.summary || value.text || value.title || '').trim()
    const suggestion = String(value.suggestion || value.recommendation || '').trim()
    return [summary, suggestion ? `建议：${suggestion}` : ''].filter(Boolean).join('。') || '进入患者详情复核。'
  }
  const text = String(value || '').trim()
  if (!text) return '暂无一句话理由'
  if (text.includes("'summary'") || text.includes('"summary"')) return '综合风险推理已生成结论，点击进入患者详情查看证据和建议。'
  return text
}
async function load() {
  if (!userId.value) {
    error.value = '未识别当前账号。'
    return
  }
  loading.value = true
  error.value = ''
  try {
    const { data } = await getDoctorHome({ user_id: userId.value })
    home.value = data?.data || {}
    auth.updateAccount(home.value?.account)
  } catch (err: any) {
    error.value = err?.message || '医生首页加载失败'
  } finally {
    loading.value = false
  }
}
function tick() {
  clock.value = new Date().toLocaleString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}
onMounted(() => {
  auth.hydrateFromQuery(route.query)
  cleanDuplicateIdentityQuery()
  tick()
  timer = setInterval(tick, 1000)
  void load()
})
onUnmounted(() => clearInterval(timer))

function cleanDuplicateIdentityQuery() {
  const query = auth.cleanIdentityQuery(route.query)
  if (JSON.stringify(query) !== JSON.stringify(route.query)) router.replace({ path: route.path, query })
}
</script>

<style scoped>
.role-home { padding: 14px; display: grid; gap: 12px; }
.home-top { min-height: 72px; display: flex; justify-content: space-between; align-items: center; gap: 16px; padding: 14px; border: 1px solid rgba(125,211,252,.14); border-radius: 8px; background: rgba(7,20,34,.82); }
.home-top div { display: grid; gap: 4px; }
.home-top span, .panel-head span, .focus-row span, .task-row span, .empty { color: #8eaabd; font-size: 12px; }
.home-top strong { color: #f8fbff; font-size: 20px; }
.top-meta { display: flex !important; flex-direction: row; align-items: center; flex-wrap: wrap; }
button { min-height: 44px; border-radius: 8px; border: 1px solid rgba(125,211,252,.2); background: rgba(13,44,66,.78); color: #eafcff; padding: 0 12px; cursor: pointer; }
.doctor-grid { height: calc(100vh - 224px); min-height: 560px; display: grid; grid-template-columns: 1fr 1fr; grid-template-rows: 1fr 1fr; gap: 12px; }
.panel { min-width: 0; overflow: auto; display: grid; align-content: start; gap: 10px; padding: 12px; border: 1px solid rgba(125,211,252,.14); border-radius: 8px; background: rgba(6,18,31,.74); }
.panel-head { display: flex; justify-content: space-between; gap: 10px; align-items: baseline; }
.panel-head strong { color: #f4fbff; font-size: 15px; }
.focus-row, .task-row { display: grid; grid-template-columns: 4px minmax(0,1fr) auto; gap: 10px; align-items: center; padding: 10px; border-radius: 8px; background: rgba(11,33,50,.72); cursor: pointer; }
.focus-row i { width: 4px; height: 100%; min-height: 42px; border-radius: 999px; background: #94a3b8; }
.focus-row strong, .task-row strong { color: #eef8ff; font-size: 13px; }
.focus-row b { color: #fff; }
.tone-critical { background: #ef4444 !important; }
.tone-warning { background: #f59e0b !important; }
.tone-info { background: #38bdf8 !important; }
.kpi-grid { display: grid; grid-template-columns: repeat(4,minmax(0,1fr)); gap: 8px; }
.kpi { padding: 10px; border-radius: 8px; background: rgba(11,33,50,.72); }
.kpi span { color: #91adbd; font-size: 12px; }
.kpi strong { display: block; color: #f8fbff; font-size: 24px; margin-top: 4px; }
.full-btn { width: 100%; }
.task-list { display: grid; gap: 8px; }
.task-row { grid-template-columns: minmax(0,1fr); cursor: default; }
.lights { display: grid; grid-template-columns: repeat(3,minmax(0,1fr)); gap: 8px; }
.light { display: grid; justify-items: start; align-content: center; gap: 4px; background: rgba(11,33,50,.72); }
.light b { font-size: 18px; }
.is-green { border-color: rgba(52,211,153,.35); }
.is-yellow { border-color: rgba(245,158,11,.42); }
.empty { padding: 14px; border-radius: 8px; background: rgba(11,33,50,.58); }
.empty.small { padding: 10px; }
.empty.danger { color: #fecaca; }
@media (max-width: 1024px) { .doctor-grid { height: auto; grid-template-columns: 1fr; grid-template-rows: none; } .kpi-grid, .lights { grid-template-columns: repeat(2,minmax(0,1fr)); } }

html[data-theme='light'] .role-home {
  background:
    radial-gradient(circle at 12% 0%, rgba(37, 99, 235, 0.08), transparent 28%),
    radial-gradient(circle at 90% 10%, rgba(14, 165, 233, 0.06), transparent 32%);
}
html[data-theme='light'] .home-top,
html[data-theme='light'] .panel {
  background: rgba(255, 255, 255, 0.96);
  border-color: rgba(145, 176, 199, 0.32);
  box-shadow: 0 10px 24px rgba(37, 99, 235, 0.07), 0 1px 3px rgba(15, 23, 42, 0.04);
}
html[data-theme='light'] .home-top strong,
html[data-theme='light'] .panel-head strong,
html[data-theme='light'] .focus-row strong,
html[data-theme='light'] .task-row strong,
html[data-theme='light'] .kpi strong,
html[data-theme='light'] .light b,
html[data-theme='light'] .focus-row b {
  color: #0f172a;
}
html[data-theme='light'] .home-top span,
html[data-theme='light'] .panel-head span,
html[data-theme='light'] .focus-row span,
html[data-theme='light'] .task-row span,
html[data-theme='light'] .kpi span,
html[data-theme='light'] .empty {
  color: #64748b;
}
html[data-theme='light'] .focus-row,
html[data-theme='light'] .task-row,
html[data-theme='light'] .kpi,
html[data-theme='light'] .light,
html[data-theme='light'] .empty {
  background: #f8fafc;
  border: 1px solid rgba(145, 176, 199, 0.26);
}
html[data-theme='light'] button {
  background: #eff6ff;
  border-color: rgba(37, 99, 235, 0.18);
  color: #1d4ed8;
}
html[data-theme='light'] button:hover {
  background: #dbeafe;
  border-color: rgba(37, 99, 235, 0.3);
}
html[data-theme='light'] .empty.danger {
  color: #b91c1c;
  background: #fef2f2;
  border-color: rgba(239, 68, 68, 0.18);
}
</style>
