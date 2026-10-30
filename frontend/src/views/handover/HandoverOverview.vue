<template>
  <div class="handover-overview">
    <header class="overview-header">
      <div class="header-left">
        <h1 class="page-title">智能交接班</h1>
        <span class="dept-name">{{ deptName || '全院' }}</span>
        <span v-if="currentShift?.name" class="shift-badge">{{ currentShift.name }}<template v-if="currentShift.start_time"> {{ currentShift.start_time }}–{{ currentShift.end_time }}</template></span>
      </div>
      <div class="header-right">
        <a-button type="primary" :loading="generating" @click="onGenerate">生成并保存总结</a-button>
        <a-button :loading="loading" @click="onRefresh">刷新</a-button>
      </div>
    </header>

    <template v-if="summary">
      <!-- 结论先行：本班交接重点 -->
      <section class="ho-brief">
        <div class="ho-brief__head">
          <span class="ho-brief__title">本班交接重点</span>
          <span class="ho-brief__meta">数据 {{ fmtTime(summary.data_start) }} — {{ fmtTime(summary.data_end) }}</span>
        </div>
        <div class="ho-brief__body">
          <p class="ho-brief__headline">{{ summary.deterministic_summary || '本班暂无交班摘要' }}</p>
          <div class="ho-tiles">
            <div class="ho-tile"><span>在科患者</span><b>{{ summary.patient_count ?? '—' }}</b></div>
            <div class="ho-tile" :class="{ crit: summary.critical_patient_count }"><span>危急患者</span><b>{{ summary.critical_patient_count ?? 0 }}</b></div>
            <div class="ho-tile" :class="{ crit: summary.unclosed_alert_count }"><span>未闭环告警</span><b>{{ summary.unclosed_alert_count ?? 0 }}</b></div>
            <div class="ho-tile" :class="{ warn: summary.draft_patient_count }"><span>未完成交班</span><b>{{ summary.draft_patient_count ?? 0 }}</b></div>
            <div class="ho-tile" :class="{ warn: summary.submitted_patient_count }"><span>待签收</span><b>{{ summary.submitted_patient_count ?? 0 }}</b></div>
            <div class="ho-tile" :class="{ warn: !tasksMissing && summary.overdue_task_count }"><span>逾期任务</span><b>{{ tasksMissing ? '未接入' : (summary.overdue_task_count ?? 0) }}</b></div>
          </div>
          <div class="ho-support">
            <span class="ho-support__label">生命支持</span>
            <span class="ho-chip">呼吸机 {{ summary.ventilator_patient_count ?? 0 }}</span>
            <span class="ho-chip">血管活性药 {{ summary.vasoactive_patient_count ?? 0 }}</span>
            <span class="ho-chip">CRRT {{ summary.crrt_patient_count ?? 0 }}</span>
            <span class="ho-chip">隔离 {{ summary.isolation_patient_count ?? 0 }}</span>
            <span class="ho-chip" :class="{ warn: summary.high_risk_line_count }">高危管路 {{ summary.high_risk_line_count ?? 0 }}</span>
            <span v-if="movementText" class="ho-chip">{{ movementText }}</span>
          </div>
          <p v-if="sourceWarning" class="ho-warn">{{ sourceWarning }}</p>
          <p v-if="summary.ai_summary" class="ai-summary-text">AI 补充：{{ summary.ai_summary }}</p>
        </div>
      </section>

      <!-- 重点患者：按后端风险等级排序，列出全部判定原因 -->
      <section class="ho-card">
        <div class="ho-card__head">
          <h3>重点患者 <small>{{ focusPatients.length }} 名</small></h3>
          <span class="ho-card__hint">危急：危急值或未闭环高危告警；高危：血管活性药/CRRT/未闭环告警；中危：机械通气/高危管路</span>
        </div>
        <div v-if="focusPatients.length" class="ho-focus">
          <button v-for="p in focusPatients" :key="p.patient_id" type="button" class="ho-focus__row" :class="`lv-${p.risk_level}`" @click="goToPatient(p.patient_id)">
            <span class="ho-focus__level">{{ LEVEL_LABELS[p.risk_level] || p.risk_level }}</span>
            <span class="ho-focus__bed">{{ p.bed }}床</span>
            <span class="ho-focus__name">{{ p.name }}</span>
            <span class="ho-focus__dx">{{ p.diagnosis }}</span>
            <span class="ho-focus__reasons">
              <i v-for="r in p.reasons" :key="r">{{ r }}</i>
            </span>
            <span class="ho-focus__go">ISBAR</span>
          </button>
        </div>
        <p v-else class="ho-empty">本班无危急/高危/中危患者。</p>
      </section>

      <BedRiskMatrix
        class="ho-matrix"
        :beds="summary.patients || []"
        :time-range="`${fmtTime(summary.data_start)} — ${fmtTime(summary.data_end)}`"
        :updated-at="fmtTime(summary.created_at)"
        @select="(bed: any) => goToPatient(bed.patient_id)"
      />
      <p class="summary-meta">生成时间：{{ fmtTime(summary.created_at) || '—' }}；摘要由规则统计生成，交班内容以各患者 ISBAR 为准。</p>
    </template>

    <a-empty v-if="!loading && !summary" description="暂无交班总结数据，请点击生成" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Button as AButton, Empty as AEmpty, message } from 'ant-design-vue'
import { useAuthStore } from '../../stores/auth'
import api from '../../api'
import { BedRiskMatrix } from '../../components/handover/charts'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const loading = ref(false)
const generating = ref(false)
const summary = ref<any>(null)
const currentShift = ref<any>(null)

const deptCode = computed(() => authStore.deptCode || (route.query.dept_code as string) || '')
const deptName = computed(() => authStore.dept || (route.query.dept as string) || '')

const LEVEL_LABELS: Record<string, string> = { critical: '危急', high: '高危', medium: '中危', stable: '平稳' }
const LEVEL_RANK: Record<string, number> = { critical: 0, high: 1, medium: 2 }
// 重点患者：直接使用后端 risk_level / risk_reasons，不在前端另造“风险分”
const focusPatients = computed(() => {
  const list = Array.isArray(summary.value?.patients) ? summary.value.patients : []
  return list
    .filter((p: any) => p && p.risk_level in LEVEL_RANK)
    .map((p: any) => ({
      ...p,
      reasons: Array.isArray(p.risk_reasons) && p.risk_reasons.length ? p.risk_reasons : [p.is_critical ? '危急患者' : '需关注'],
    }))
    .sort((a: any, b: any) => (LEVEL_RANK[a.risk_level] ?? 9) - (LEVEL_RANK[b.risk_level] ?? 9) || String(a.bed).localeCompare(String(b.bed), 'zh', { numeric: true }))
})
const tasksMissing = computed(() => (summary.value?.missing_sources || []).includes('tasks'))
const SOURCE_LABELS: Record<string, string> = { tasks: '任务', alerts: '告警', orders: '医嘱', handovers: '交班记录', devices: '设备', labs: '检验', vitals: '体征' }
const sourceWarning = computed(() => {
  const miss = (summary.value?.missing_sources || []).map((x: string) => SOURCE_LABELS[x] || x)
  const fail = (summary.value?.failed_sources || []).map((x: string) => SOURCE_LABELS[x] || x)
  const parts: string[] = []
  if (fail.length) parts.push(`读取失败：${fail.join('、')}`)
  if (miss.length) parts.push(`未接入：${miss.join('、')}`)
  return parts.length ? `数据来源提示 — ${parts.join('；')}。相关数字不代表 0。` : ''
})
const movementText = computed(() => {
  const s = summary.value || {}
  const bits: string[] = []
  if (s.new_admission_count) bits.push(`新入 ${s.new_admission_count}`)
  if (s.transfer_in_count) bits.push(`转入 ${s.transfer_in_count}`)
  if (s.transfer_out_count) bits.push(`转出 ${s.transfer_out_count}`)
  if (s.death_count) bits.push(`死亡 ${s.death_count}`)
  return bits.join(' · ')
})
function fmtTime(t: unknown): string {
  if (!t) return ''
  const d = new Date(String(t))
  if (Number.isNaN(d.getTime())) return String(t)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

async function loadSummary() {
  loading.value = true
  try {
    const res = await api.get('/api/handover/shifts/current/summary', {
      params: { dept_code: deptCode.value }
    })
    summary.value = res.data?.summary || null
  } catch (e: any) {
    console.error('Failed to load summary:', e)
  } finally {
    loading.value = false
  }
}

async function loadCurrentShift() {
  try {
    const res = await api.get('/api/handover/shifts/current')
    currentShift.value = res.data || null
  } catch {}
}

async function onGenerate() {
  generating.value = true
  try {
    const res = await api.post('/api/handover/shifts/current/generate', null, {
      params: {
        dept_code: deptCode.value,
        operator: authStore.effectiveUserId || '',
      }
    })
    summary.value = res.data?.summary || null
    message.success('交班总结已生成')
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '生成失败')
  } finally {
    generating.value = false
  }
}

function onRefresh() {
  loadSummary()
  loadCurrentShift()
}

function goToPatient(patientId: string) {
  router.push({ name: 'handover-patient', params: { patientId } })
}

onMounted(() => {
  loadCurrentShift()
  loadSummary()
})
</script>

<style scoped>
.handover-overview {
  padding: var(--page-padding, 24px);
  max-width: 1400px;
  width: 100%;
  box-sizing: border-box;
  margin: 0 auto;
}

.overview-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.page-title {
  font-size: var(--text-page-title);
  font-weight: var(--text-page-title-weight);
  color: var(--color-text-primary);
  margin: 0;
}

.dept-name {
  font-size: var(--text-page-subtitle);
  color: var(--color-text-secondary);
}

.shift-badge {
  background: var(--color-primary-bg);
  color: var(--color-primary);
  padding: 2px 8px;
  border-radius: var(--radius-tag);
  font-size: var(--text-label);
  font-weight: var(--weight-medium);
}

.stats-row {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 14px;
  margin-bottom: 20px;
}

.stat-card {
  display: flex;
  flex-direction: column;
  background: var(--color-bg-surface);
  border-radius: var(--radius-lg);
  padding: 14px 16px;
  text-align: left;
  border: 1px solid var(--color-border);
}

.stat-value {
  font-size: var(--text-metric-key);
  font-weight: var(--weight-bold);
  font-variant-numeric: tabular-nums;
  color: var(--color-text-primary);
  line-height: 1.2;
}

.stat-label {
  order: -1;
  font-size: var(--text-caption);
  font-weight: var(--weight-medium);
  color: var(--color-text-secondary);
  margin-bottom: 4px;
}

.stat-card--critical .stat-value { color: var(--color-danger); }
.stat-card--warning .stat-value { color: var(--color-warning); }
.stat-card--info .stat-value { color: var(--color-info); }
.stat-card--alert .stat-value { color: var(--color-danger); }
.stat-card--task .stat-value { color: var(--color-warning); }

.summary-card, .priority-card, .life-support-row, .charts-row {
  margin-bottom: 16px;
}

.charts-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.summary-text {
  font-size: 14px;
  line-height: 1.8;
  color: var(--color-text-primary);
}

.ai-summary-text {
  font-size: 14px;
  line-height: 1.8;
  color: var(--color-ai);
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed var(--color-border);
}

.summary-meta {
  font-size: 12px;
  color: var(--color-text-tertiary);
  margin-top: 12px;
}

.ls-grid {
  display: flex;
  gap: 24px;
}

.ls-item {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.ls-value {
  font-size: var(--text-metric-normal);
  font-weight: var(--weight-semibold);
  font-variant-numeric: tabular-nums;
  color: var(--color-text-primary);
}

.ls-label {
  font-size: var(--text-caption);
  color: var(--color-text-secondary);
}

@media (max-width: 768px) {
  .stats-row {
    grid-template-columns: repeat(2, 1fr);
  }
  .charts-row {
    grid-template-columns: 1fr;
  }
  .handover-overview {
    padding: 12px;
  }
}

.ho-brief, .ho-card { background: #fff; border: 1px solid #E6E5E3; border-radius: 10px; overflow: hidden; margin-bottom: 14px; }
.ho-brief__head { height: 38px; background: #5392FF; color: #fff; display: flex; align-items: center; justify-content: space-between; padding: 0 16px; }
.ho-brief__title { font-size: 15px; font-weight: 600; }
.ho-brief__meta { font-size: 12px; opacity: .9; }
.ho-brief__body { padding: 14px 16px; }
.ho-brief__headline { margin: 0 0 12px; font-size: 16px; font-weight: 600; line-height: 1.6; color: #1F2329; }
.ho-tiles { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 10px; }
.ho-tile { background: #F7F8FA; border: 1px solid #EBEDF0; border-radius: 8px; padding: 8px 12px; display: flex; flex-direction: column; }
.ho-tile span { font-size: 12px; color: #646A73; }
.ho-tile b { font-size: 22px; font-variant-numeric: tabular-nums; color: #1F2329; }
.ho-tile.crit { background: #FEF2F2; border-color: #FCA5A5; } .ho-tile.crit b { color: #B91C1C; }
.ho-tile.warn { background: #FFFBEB; border-color: #FCD34D; } .ho-tile.warn b { color: #B45309; }
.ho-support { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin-top: 12px; }
.ho-support__label { font-size: 12px; color: #646A73; margin-right: 2px; }
.ho-chip { font-size: 12px; padding: 2px 8px; border-radius: 4px; background: #F2F3F5; color: #1F2329; border: 1px solid #E6E5E3; }
.ho-chip.warn { background: #FFFBEB; color: #B45309; border-color: #FCD34D; }
.ho-warn { margin: 10px 0 0; font-size: 12px; color: #B45309; }
.ho-card__head { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; padding: 12px 16px; border-bottom: 1px solid #EFF0F1; }
.ho-card__head h3 { margin: 0; font-size: 15px; font-weight: 600; border-left: 3px solid #5392FF; padding-left: 8px; }
.ho-card__head small { font-weight: 400; color: #8F959E; margin-left: 4px; }
.ho-card__hint { font-size: 12px; color: #8F959E; }
.ho-focus { display: flex; flex-direction: column; }
.ho-focus__row { display: grid; grid-template-columns: 52px 56px 72px minmax(120px, 220px) 1fr 52px; gap: 10px; align-items: center; padding: 9px 16px; border: 0; border-bottom: 1px solid #F2F3F5; background: #fff; text-align: left; cursor: pointer; font: inherit; }
.ho-focus__row:hover { background: #F5F8FF; }
.ho-focus__level { font-size: 12px; font-weight: 700; text-align: center; border-radius: 4px; padding: 1px 0; }
.lv-critical .ho-focus__level { background: #FEF2F2; color: #B91C1C; }
.lv-high .ho-focus__level { background: #FFF7ED; color: #C2410C; }
.lv-medium .ho-focus__level { background: #FFFBEB; color: #B45309; }
.ho-focus__bed { font-weight: 700; color: #1F2329; }
.ho-focus__name { color: #1F2329; }
.ho-focus__dx { color: #646A73; font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ho-focus__reasons { display: flex; flex-wrap: wrap; gap: 4px; }
.ho-focus__reasons i { font-style: normal; font-size: 12px; padding: 1px 6px; border-radius: 4px; background: #F2F3F5; color: #1F2329; }
.lv-critical .ho-focus__reasons i:first-child { background: #FEF2F2; color: #B91C1C; }
.ho-focus__go { font-size: 12px; color: #5392FF; text-align: right; }
.ho-empty { padding: 16px; margin: 0; color: #8F959E; font-size: 13px; }
.ho-matrix { margin-bottom: 8px; }
@media (max-width: 900px) { .ho-tiles { grid-template-columns: repeat(3, minmax(0, 1fr)); } .ho-focus__row { grid-template-columns: 52px 56px 1fr; } .ho-focus__dx, .ho-focus__reasons, .ho-focus__go { grid-column: 1 / -1; } }
</style>
