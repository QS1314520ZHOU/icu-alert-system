<template>
  <div class="similar-cases">
    <!-- 概览行 -->
    <div class="sc-overview-row">
      <div class="sc-stat-card">
        <span class="sc-stat-value">{{ summary.matched_cases || 0 }}</span>
        <span class="sc-stat-label">匹配病例</span>
      </div>
      <div class="sc-stat-card">
        <span class="sc-stat-value">{{ avgSimilarity }}%</span>
        <span class="sc-stat-label">平均相似度</span>
      </div>
      <div class="sc-stat-card">
        <span class="sc-stat-value">{{ summary.data_range || '—' }}</span>
        <span class="sc-stat-label">数据范围</span>
      </div>
      <div class="sc-stat-card">
        <span class="sc-stat-value">{{ comparabilityScore }}%</span>
        <span class="sc-stat-label">可比性评分</span>
      </div>
    </div>

    <!-- 分布图 + 雷达图 -->
    <div class="sc-chart-row">
      <div class="sc-chart-card">
        <h3 class="sc-chart-title">相似病例分布</h3>
        <div ref="scatterRef" class="sc-chart-area"></div>
      </div>
      <div class="sc-chart-card">
        <h3 class="sc-chart-title">特征对比</h3>
        <div ref="radarRef" class="sc-chart-area"></div>
      </div>
    </div>

    <!-- 结局分布 -->
    <div class="sc-chart-row">
      <div class="sc-chart-card">
        <h3 class="sc-chart-title">结局分布</h3>
        <div class="sc-outcome-grid">
          <div class="sc-outcome-item" v-for="oc in outcomes" :key="oc.label">
            <div class="sc-outcome-bar">
              <div class="sc-outcome-fill" :style="{ width: oc.pct + '%' }" :class="`sc-outcome-fill--${oc.level}`"></div>
            </div>
            <span class="sc-outcome-label">{{ oc.label }}</span>
            <span class="sc-outcome-value">{{ oc.pct }}%</span>
          </div>
        </div>
      </div>
      <div class="sc-chart-card">
        <h3 class="sc-chart-title">ICU住院时间分布</h3>
        <div ref="losRef" class="sc-chart-area"></div>
      </div>
    </div>

    <!-- 相似病例卡片 -->
    <div class="sc-cases-section">
      <h3 class="sc-section-title">相似病例列表</h3>
      <div class="sc-cases-grid">
        <div v-for="c in cases" :key="c.case_id" class="sc-case-card">
          <div class="sc-case-header">
            <span class="sc-case-id">{{ c.case_id }}</span>
            <span class="sc-case-similarity" :class="similarityClass(c.similarity)">{{ (c.similarity * 100).toFixed(0) }}%</span>
          </div>
          <div class="sc-case-body">
            <div class="sc-case-row"><span>年龄差</span><span>{{ c.age_diff || '—' }}岁</span></div>
            <div class="sc-case-row"><span>SOFA差</span><span>{{ c.sofa_diff || '—' }}</span></div>
            <div class="sc-case-row"><span>器官支持</span><span>{{ c.organ_support || '—' }}</span></div>
            <div class="sc-case-row"><span>主要治疗</span><span>{{ c.primary_treatment || '—' }}</span></div>
            <div class="sc-case-row"><span>结局</span><span :class="outcomeClass(c.outcome)">{{ c.outcome || '—' }}</span></div>
          </div>
          <div class="sc-case-footer">
            <button class="sc-case-btn" @click="openWhatIf(c)">What-if</button>
            <button class="sc-case-btn" @click="openCausal(c)">因果推断</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useEmbedBridge } from '../../../composables/useEmbedBridge'
import { getPatientSimilarCaseOutcomes } from '../../../api'

const route = useRoute()
const patientId = computed(() => String(route.params.patientId || ''))

const { sendUpdateTitle, sendNavigateModule, sendReportError } = useEmbedBridge({
  moduleKey: 'similar-cases',
  targetOrigin: '*',
  onPatientContextChanged: () => loadData(),
  onRefresh: () => loadData(),
})

const loading = ref(false)
const reviewData = ref<any>(null)

const summary = computed(() => reviewData.value?.summary || {})
const cases = computed(() => reviewData.value?.cases || [])
const avgSimilarity = computed(() => {
  const cs = cases.value
  if (!cs.length) return 0
  const avg = cs.reduce((s: number, c: any) => s + (c.similarity || 0), 0) / cs.length
  return (avg * 100).toFixed(0)
})
const comparabilityScore = computed(() => {
  return summary.value?.comparability_score ? (summary.value.comparability_score * 100).toFixed(0) : '—'
})

const outcomes = computed(() => {
  const oc = summary.value?.outcome_distribution || {}
  return [
    { label: '存活', pct: oc.survival ?? 0, level: 'good' },
    { label: 'CRRT', pct: oc.crrt ?? 0, level: 'warn' },
    { label: '撤机成功', pct: oc.weaning_success ?? 0, level: 'good' },
    { label: '肾功能恢复', pct: renalRecovery ?? 0, level: 'good' },
  ]
})

const renalRecovery = computed(() => summary.value?.outcome_distribution?.renal_recovery ?? 0)

const scatterRef = ref<HTMLElement | null>(null)
const radarRef = ref<HTMLElement | null>(null)
const losRef = ref<HTMLElement | null>(null)

function similarityClass(s: number) {
  if (s >= 0.8) return 'sc-sim-high'
  if (s >= 0.6) return 'sc-sim-medium'
  return 'sc-sim-low'
}

function outcomeClass(o: string) {
  const s = String(o || '').toLowerCase()
  if (s.includes('死亡') || s.includes('death')) return 'sc-outcome-bad'
  if (s.includes('恢复') || s.includes('recovery')) return 'sc-outcome-good'
  return ''
}

function openWhatIf(c: any) {
  sendNavigateModule('what-if', patientId.value)
}

function openCausal(c: any) {
  sendNavigateModule('causal-inference', patientId.value)
}

async function loadData() {
  if (!patientId.value) return
  loading.value = true
  try {
    const res = await getPatientSimilarCaseOutcomes(patientId.value, 10)
    reviewData.value = res.data?.review || null
  } catch (e: any) {
    sendReportError('LOAD_FAILED', e?.message || '加载相似病例失败')
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  sendUpdateTitle('相似病例')
  loadData()
})
</script>

<style scoped>
.similar-cases {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.sc-overview-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}

.sc-stat-card {
  background: #fff;
  border-radius: 8px;
  padding: 16px;
  border: 1px solid var(--border, #DCE3EC);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.sc-stat-value {
  font-size: 28px;
  font-weight: 700;
  font-family: var(--font-digit, monospace);
  color: var(--primary, #2563EB);
}

.sc-stat-label {
  font-size: 12px;
  color: var(--text-secondary, #52606D);
}

.sc-chart-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.sc-chart-card {
  background: #fff;
  border-radius: 8px;
  padding: 16px;
  border: 1px solid var(--border, #DCE3EC);
}

.sc-chart-title {
  margin: 0 0 12px;
  font-size: 14px;
  font-weight: 600;
}

.sc-chart-area {
  height: 260px;
}

/* 结局 */
.sc-outcome-grid {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 8px 0;
}

.sc-outcome-item {
  display: grid;
  grid-template-columns: 1fr 80px 50px;
  align-items: center;
  gap: 8px;
}

.sc-outcome-bar {
  height: 8px;
  background: #E8EEF5;
  border-radius: 4px;
  overflow: hidden;
}

.sc-outcome-fill {
  height: 100%;
  border-radius: 4px;
  transition: width 0.6s ease;
}

.sc-outcome-fill--good { background: #16A34A; }
.sc-outcome-fill--warn { background: #F59E0B; }
.sc-outcome-fill--bad { background: #DC2626; }

.sc-outcome-label {
  font-size: 12px;
  color: var(--text-secondary, #52606D);
}

.sc-outcome-value {
  font-size: 13px;
  font-weight: 600;
  font-family: var(--font-digit, monospace);
  text-align: right;
}

/* 病例卡片 */
.sc-section-title {
  margin: 0 0 12px;
  font-size: 14px;
  font-weight: 600;
}

.sc-cases-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
}

.sc-case-card {
  background: #fff;
  border-radius: 8px;
  border: 1px solid var(--border, #DCE3EC);
  overflow: hidden;
}

.sc-case-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 14px;
  background: #F8FAFC;
  border-bottom: 1px solid var(--border, #DCE3EC);
}

.sc-case-id {
  font-size: 13px;
  font-weight: 600;
  font-family: var(--font-mono, monospace);
}

.sc-case-similarity {
  font-size: 13px;
  font-weight: 700;
  font-family: var(--font-digit, monospace);
}

.sc-sim-high { color: #16A34A; }
.sc-sim-medium { color: #F59E0B; }
.sc-sim-low { color: #94A3B8; }

.sc-case-body {
  padding: 10px 14px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.sc-case-row {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
}

.sc-case-row span:first-child { color: var(--text-secondary, #52606D); }
.sc-case-row span:last-child { font-weight: 500; }

.sc-outcome-good { color: #16A34A; }
.sc-outcome-bad { color: #DC2626; }

.sc-case-footer {
  display: flex;
  gap: 8px;
  padding: 8px 14px 12px;
}

.sc-case-btn {
  flex: 1;
  padding: 6px;
  font-size: 12px;
  border: 1px solid var(--border, #DCE3EC);
  border-radius: 4px;
  background: #fff;
  cursor: pointer;
  transition: all 0.15s;
}

.sc-case-btn:hover {
  background: var(--primary-light, #EFF6FF);
  border-color: var(--primary, #2563EB);
  color: var(--primary, #2563EB);
}

@media (max-width: 1200px) {
  .sc-chart-row { grid-template-columns: 1fr; }
  .sc-overview-row { grid-template-columns: repeat(2, 1fr); }
}
</style>
