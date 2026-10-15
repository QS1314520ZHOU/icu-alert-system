<template>
  <div class="intelligence-layout">
    <PageHeader title="智能研判" subtitle="数字孪生与 AI 研判结论" />
    <a-tabs v-model:activeKey="activeTab" type="card">
      <!-- 数字孪生 -->
      <a-tab-pane key="digital-twin" tab="数字孪生">
        <Suspense>
          <DigitalTwinTab :patient-id="patientId" :patient="patient" />
          <template #fallback><div class="loading-placeholder"><a-spin tip="加载数字孪生..." /></div></template>
        </Suspense>
      </a-tab-pane>

      <!-- 相似病例 -->
      <a-tab-pane key="similar-cases" tab="相似病例">
        <Suspense>
          <SimilarCasesTab :review="similarCaseReview" :loading="similarCaseLoading" :error="similarCaseError" :on-refresh="() => {}" :fmt-time="(v: any) => v ? new Date(v).toLocaleString('zh-CN') : '—'" />
          <template #fallback><div class="loading-placeholder"><a-spin tip="加载相似病例..." /></div></template>
        </Suspense>
      </a-tab-pane>

      <!-- 风险预测（复用 usePatientDetail 中的 aiRisk 状态） -->
      <a-tab-pane key="risk-forecast" tab="风险预测">
        <section class="intel-section">
          <div class="section-header">
            <h3>AI 风险预测</h3>
            <a-button size="small" @click="loadAiRisk" :loading="aiRiskLoading">刷新</a-button>
          </div>
          <div v-if="aiRiskForecast" class="risk-detail">
            <div class="risk-summary">
              <p>{{ aiRiskText || '暂无风险摘要' }}</p>
            </div>
            <div v-if="organRows.length" class="organ-assessment">
              <h4>器官风险评估</h4>
              <div class="organ-grid">
                <div v-for="organ in organRows" :key="organ.key" class="organ-item" :class="organClass(organ)">
                  <span class="organ-name">{{ organ.label }}</span>
                  <span class="organ-status">{{ organ.status_text }}</span>
                  <p v-if="organ.evidence" class="organ-evidence">{{ organ.evidence }}</p>
                </div>
              </div>
            </div>
            <div v-if="aiRiskForecast.forecast_data" class="risk-raw">
              <CollapseSection>
                <template #title><span style="font-size:13px;font-weight:600">预测数据详情</span></template>
                <pre class="risk-raw-data">{{ JSON.stringify(aiRiskForecast.forecast_data, null, 2) }}</pre>
              </CollapseSection>
            </div>
          </div>
          <a-empty v-else-if="!aiRiskLoading" description="暂无风险预测数据" :image-style="{ height: '40px' }" />
        </section>
      </a-tab-pane>

      <!-- 因果分析 -->
      <a-tab-pane key="causal" tab="因果分析">
        <section class="intel-section">
          <div class="section-header">
            <h3>因果推理分析</h3>
            <a-button size="small" @click="loadCausal" :loading="causalLoading">生成分析</a-button>
          </div>
          <div v-if="causalResult" class="causal-detail">
            <div v-if="causalResult.causal_chain" class="causal-chain">
              <h4>因果链</h4>
              <p>{{ causalResult.causal_chain }}</p>
            </div>
            <div v-if="causalResult.intervention_suggestions?.length" class="causal-suggestions">
              <h4>干预建议</h4>
              <ul>
                <li v-for="(s, i) in causalResult.intervention_suggestions" :key="i">{{ s }}</li>
              </ul>
            </div>
            <div v-if="causalResult.risk_factors?.length" class="causal-risk-factors">
              <h4>风险因素</h4>
              <div class="risk-factor-list">
                <a-tag v-for="(f, i) in causalResult.risk_factors" :key="i" color="orange">{{ f }}</a-tag>
              </div>
            </div>
            <CollapseSection v-if="causalResult.raw_analysis">
              <template #title><span style="font-size:13px;font-weight:600">完整分析</span></template>
              <div class="causal-raw" v-html="causalResult.raw_analysis"></div>
            </CollapseSection>
          </div>
          <a-empty v-else-if="!causalLoading" description='点击"生成分析"获取因果推理' :image-style="{ height: '40px' }" />
        </section>
      </a-tab-pane>
    </a-tabs>
  </div>
</template>

<script setup lang="ts">
import { Button as AButton, Empty as AEmpty, Spin as ASpin, TabPane as ATabPane, Tabs as ATabs, Tag as ATag } from 'ant-design-vue'
import { PageHeader } from '../../components/common/design-system'
import { ref, computed, onMounted, defineAsyncComponent } from 'vue'
import { useRoute } from 'vue-router'
import { usePatientDetail } from '../../composables/usePatientDetail'
import CollapseSection from '../../components/common/CollapseSection.vue'
import { postAiCausalAnalysis } from '../../api/index'

const DigitalTwinTab = defineAsyncComponent(() => import('../../components/patient-detail/DigitalTwinTab.vue'))
const SimilarCasesTab = defineAsyncComponent(() => import('../../components/patient-detail/SimilarCasesTab.vue'))

const route = useRoute()
const {
  patient,
  aiRiskForecast, aiRiskText, aiRiskLoading,
  loadAiRisk, aiRiskOrganRows,
  similarCaseReview, similarCaseLoading, similarCaseError,
} = usePatientDetail()

const patientId = computed(() => String(route.params.patientId || route.params.id || ''))
const activeTab = ref('digital-twin')

// 复用 composable 的器官评估行
const organRows = computed(() => aiRiskOrganRows(aiRiskForecast.value))

// ── Causal Analysis ─────────────────────────────────────
const causalResult = ref<any>(null)
const causalLoading = ref(false)

async function loadCausal() {
  if (!patientId.value) return
  causalLoading.value = true
  try {
    const abnormalFinding = patient.value?.diagnosis || aiRiskText.value || '患者综合评估'
    const res = await postAiCausalAnalysis(patientId.value, { abnormal_finding: abnormalFinding })
    causalResult.value = res?.data?.data || res?.data || null
  } catch (e) {
    console.warn('[IntelligenceView] causal analysis failed:', e)
  } finally {
    causalLoading.value = false
  }
}

function organClass(organ: any) {
  const s = String(organ.status_text || '').toLowerCase()
  if (s.includes('衰竭') || s.includes('failure') || s.includes('危')) return 'organ-critical'
  if (s.includes('受损') || s.includes('impaired') || s.includes('风险')) return 'organ-warning'
  return 'organ-normal'
}

onMounted(() => {
  loadAiRisk()
})
</script>

<style scoped>
.intelligence-layout {
  padding: 0;
}

.loading-placeholder {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 200px;
}

.intel-section {
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: 16px 20px;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.section-header h3 {
  margin: 0;
  font-size: var(--text-section-title);
  font-weight: 600;
  color: var(--color-text-primary);
}

/* Risk Forecast */
.risk-detail {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.risk-summary p {
  margin: 0;
  font-size: var(--text-body);
  color: var(--color-text-primary);
  line-height: 1.6;
}

.organ-assessment h4 {
  margin: 0 0 10px;
  font-size: var(--text-body);
  font-weight: 600;
}

.organ-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 10px;
}

.organ-item {
  padding: 10px 12px;
  border: 1px solid var(--color-divider);
  border-radius: var(--radius-md);
  background: var(--color-bg-surface-secondary);
}

.organ-name {
  font-size: var(--text-label);
  color: var(--color-text-secondary);
  font-weight: 500;
}

.organ-status {
  display: block;
  font-size: var(--text-body);
  font-weight: 700;
  margin: 4px 0;
}

.organ-critical { border-left: 3px solid var(--color-danger); }
.organ-critical .organ-status { color: var(--color-danger); }
.organ-warning { border-left: 3px solid var(--color-high-risk); }
.organ-warning .organ-status { color: var(--color-high-risk); }
.organ-normal { border-left: 3px solid var(--color-normal); }
.organ-normal .organ-status { color: var(--color-normal); }

.organ-evidence {
  margin: 4px 0 0;
  font-size: var(--text-caption);
  color: var(--color-text-tertiary);
  line-height: 1.4;
}

.risk-raw-data {
  font-size: var(--text-caption);
  color: var(--color-text-secondary);
  background: var(--color-bg-surface-secondary);
  padding: 10px;
  border-radius: var(--radius-tag);
  white-space: pre-wrap;
  max-height: 300px;
  overflow: auto;
}

/* Causal Analysis */
.causal-detail {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.causal-detail h4 {
  margin: 0 0 8px;
  font-size: var(--text-body);
  font-weight: 600;
  color: var(--color-text-primary);
}

.causal-chain p {
  margin: 0;
  font-size: var(--text-body);
  color: var(--color-text-primary);
  line-height: 1.6;
  padding: 10px;
  background: var(--color-bg-surface-secondary);
  border-radius: var(--radius-md);
}

.causal-suggestions ul {
  margin: 0;
  padding-left: 20px;
}

.causal-suggestions li {
  font-size: var(--text-body);
  color: var(--color-text-primary);
  line-height: 1.8;
}

.risk-factor-list {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.causal-raw {
  font-size: var(--text-body);
  line-height: 1.6;
  color: var(--color-text-primary);
}
</style>

