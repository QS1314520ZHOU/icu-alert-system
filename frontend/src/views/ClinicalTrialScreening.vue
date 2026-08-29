<template>
  <div class="trial-page">
    <PageHeader title="临床试验智能筛选" subtitle="维护入排标准，自动扫描 ICU 患者，只提示可能符合，不自动入组">
      <template #actions>
        <a-button :loading="loading" @click="loadAll">刷新</a-button>
        <a-button type="primary" :loading="screening" @click="screen">立即筛选</a-button>
      </template>
    </PageHeader>

    <MetricStrip :metrics="kpiMetrics" />

    <!-- 筛选漏斗可视化 -->
    <div v-if="trials.length" class="trial-viz-row">
      <div class="trial-viz-card">
        <h4>筛选漏斗</h4>
        <div ref="funnelChartRef" class="trial-viz-chart"></div>
      </div>
      <div class="trial-viz-card trial-viz-card--ring">
        <h4>数据完整性</h4>
        <DataCompletenessRing :value="screeningCompleteness" :size="100" />
        <span class="trial-viz-ring-label">{{ trials.length }} 项试验</span>
      </div>
    </div>

    <!-- 步骤式流程 -->
    <div class="step-card">
      <a-steps :current="currentStep" size="small" :items="stepItems" />
    </div>

    <!-- 步骤1：选择试验 -->
    <div v-show="currentStep === 0" class="step-panel">
      <SectionHeader title="临床试验列表" description="选择或新建试验，启用招募后参与筛选">
        <template #actions>
          <a-space>
            <a-button size="small" :loading="demoLoading" @click="createDemoTrial">演示模板</a-button>
            <a-button size="small" type="primary" @click="openNewTrial">新建</a-button>
          </a-space>
        </template>
      </SectionHeader>

      <template v-if="trials.length">
        <div class="trial-grid">
          <article v-for="trial in trials" :key="trial.trial_id" class="trial-card" :class="{ selected: selectedTrialId === trial.trial_id }" @click="selectTrial(trial)">
            <div class="trial-card-head">
              <a-tag :color="trial.status === '招募中' ? 'green' : 'gold'">{{ trial.status || '准备中' }}</a-tag>
              <span class="trial-reg">{{ trial.registration_no || '未登记' }}</span>
            </div>
            <h3>{{ trial.trial_name }}</h3>
            <p>PI：{{ trial.pi || '未指定' }} · {{ trial.study_type || '' }}</p>
            <div class="rule-summary">
              <span>入组 {{ trial.inclusion_rules?.length || 0 }} 条</span>
              <span>排除 {{ trial.exclusion_rules?.length || 0 }} 条</span>
            </div>
            <div class="trial-actions" @click.stop>
              <a-button size="small" type="primary" ghost @click="activate(trial)">启用招募</a-button>
              <a-button size="small" @click="openParse(trial)">AI 解析</a-button>
              <a-button size="small" @click="editTrial(trial)">编辑</a-button>
              <a-button size="small" danger ghost @click="removeTrial(trial)">删除</a-button>
            </div>
          </article>
        </div>
        <ActionBar>
          <a-button type="primary" :disabled="!selectedTrialId" @click="nextStep">查看候选患者 →</a-button>
        </ActionBar>
      </template>

      <EmptyState v-else-if="!loading" title="暂无试验配置" description="新建试验并设置入排规则，或使用演示模板快速开始">
        <template #action>
          <a-space>
            <a-button type="primary" :loading="demoLoading" @click="createDemoTrial">创建示例试验</a-button>
            <a-button @click="openNewTrial">手动新建</a-button>
          </a-space>
        </template>
      </EmptyState>
    </div>

    <!-- 步骤2：候选患者 -->
    <div v-show="currentStep === 1" class="step-panel">
      <SectionHeader title="候选患者" description="仅表示可能符合，需医生人工确认">
        <template #actions>
          <a-button size="small" @click="prevStep">← 返回试验列表</a-button>
        </template>
      </SectionHeader>

      <template v-if="candidates.length">
        <div class="candidate-table-wrap">
          <a-table :data-source="candidateRows" :columns="candidateColumns" :pagination="{ pageSize: 10, hideOnSinglePage: true }" row-key="candidate_id" size="small">
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'patient'">
                <div class="patient-cell">
                  <span class="bed-badge">{{ record.bed_no || '--' }}床</span>
                  <span>{{ record.patient_name || '脱敏患者' }}</span>
                </div>
              </template>
              <template v-else-if="column.key === 'match_pct'">
                <span class="match-pct">{{ Math.round((record.match_evidence?.confidence || 0) * 100) }}%</span>
              </template>
              <template v-else-if="column.key === 'main_criteria'">
                <div class="criteria-cell">
                  <span v-for="(item, idx) in (record.match_evidence?.matched_inclusion || []).slice(0, 3)" :key="idx" class="criteria-tag">
                    {{ ruleText(item) }}
                  </span>
                  <span v-if="!(record.match_evidence?.matched_inclusion || []).length" class="muted">—</span>
                </div>
              </template>
              <template v-else-if="column.key === 'missing_count'">
                <a-tag :color="(record.match_evidence?.missing_data?.length || 0) > 0 ? 'orange' : 'default'">
                  {{ record.match_evidence?.missing_data?.length || 0 }} 项
                </a-tag>
              </template>
              <template v-else-if="column.key === 'exclusion_risk'">
                <span v-if="record.match_evidence?.exclusion_risk" class="exclusion-risk">{{ record.match_evidence.exclusion_risk }}</span>
                <span v-else class="muted">无</span>
              </template>
              <template v-else-if="column.key === 'status'">
                <a-tag :color="statusTagColor(record.status)">{{ statusLabel(record.status) }}</a-tag>
              </template>
              <template v-else-if="column.key === 'action'">
                <a-button size="small" @click="openCandidate(record)">详情</a-button>
              </template>
            </template>
          </a-table>
        </div>
        <ActionBar>
          <a-button @click="prevStep">上一步</a-button>
          <a-button type="primary" @click="nextStep">查看状态跟踪 →</a-button>
        </ActionBar>
      </template>

      <EmptyState v-else-if="!loading" title="暂无候选患者" :description="candidateEmptyText">
        <template #action>
          <a-button :disabled="!activeTrialCount" :loading="screening" type="primary" @click="screen">立即筛选</a-button>
        </template>
      </EmptyState>
    </div>

    <!-- 步骤3：状态跟踪 -->
    <div v-show="currentStep === 2" class="step-panel">
      <SectionHeader title="筛选状态跟踪" description="查看筛选诊断和候选状态分布" />

      <div v-if="lastScreenResult" class="diagnostics-card">
        <div class="diag-row">
          <span>扫描试验</span><strong>{{ lastScreenResult.scanned_trials || 0 }} 个</strong>
          <span>扫描患者</span><strong>{{ lastScreenResult.scanned_patients || 0 }} 人</strong>
          <span>候选</span><strong>{{ lastScreenResult.candidates?.length || 0 }} 人</strong>
        </div>
        <div v-if="screenDiagnosticText" class="diag-text">{{ screenDiagnosticText }}</div>
      </div>

      <div class="scope-note">当前筛选范围：{{ scopeLabel }}</div>

      <ActionBar>
        <a-button @click="prevStep">上一步</a-button>
        <a-button :loading="screening" @click="screen">重新筛选</a-button>
      </ActionBar>
    </div>

    <!-- 匹配详情抽屉 -->
    <a-drawer v-model:open="candidateOpen" width="640" title="匹配详情">
      <template v-if="selectedCandidate">
        <div class="match-detail">
          <div class="match-header">
            <h2>{{ selectedCandidate.patient_name || '脱敏患者' }}</h2>
            <a-tag color="blue">{{ statusLabel(selectedCandidate.status) }}</a-tag>
          </div>
          <p class="match-hint">{{ selectedCandidate.message || '该患者可能符合入组标准，请人工确认。' }}</p>

          <div class="match-section">
            <h3>诊断</h3>
            <p>{{ selectedCandidate.diagnosis_summary || '暂无诊断摘要' }}</p>
          </div>

          <div class="match-section">
            <h3>满足的入组标准</h3>
            <ul v-if="selectedCandidate.match_evidence?.matched_inclusion?.length">
              <li v-for="(item, idx) in selectedCandidate.match_evidence.matched_inclusion" :key="idx">{{ ruleText(item) }}</li>
            </ul>
            <p v-else class="muted">暂无明确入组证据</p>
          </div>

          <div class="match-section">
            <h3>缺失数据</h3>
            <ul v-if="selectedCandidate.match_evidence?.missing_data?.length">
              <li v-for="(item, idx) in selectedCandidate.match_evidence.missing_data" :key="idx">{{ item.reason || JSON.stringify(item.rule || item) }}</li>
            </ul>
            <p v-else class="muted">未发现关键缺失项</p>
          </div>

          <div class="match-section">
            <h3>排除标准</h3>
            <ul v-if="selectedCandidate.match_evidence?.untriggered_exclusion?.length">
              <li v-for="(item, idx) in selectedCandidate.match_evidence.untriggered_exclusion" :key="idx">{{ ruleText(item) }}</li>
            </ul>
            <p v-else class="muted">暂无排除规则</p>
          </div>

          <a-alert type="warning" show-icon message="仅提示可能符合，不自动入组" :description="selectedCandidate.match_evidence?.safety_notice || '必须由主管医生和研究团队人工确认。'" />

          <div class="status-flow">
            <span v-for="step in selectedCandidate.status_flow || []" :key="step.status" :class="{ done: step.done }">{{ step.label }}</span>
          </div>

          <ActionBar>
            <a-button @click="setCandidateStatus('notified')">已通知医生</a-button>
            <a-button type="primary" @click="setCandidateStatus('doctor_confirmed_suitable')">医生确认适合</a-button>
            <a-button danger @click="setCandidateStatus('doctor_confirmed_not_suitable')">确认不适合</a-button>
            <a-button type="primary" ghost @click="setCandidateStatus('enrolled')">已入组</a-button>
          </ActionBar>
        </div>
      </template>
    </a-drawer>

    <!-- 新建/编辑试验抽屉 -->
    <a-drawer v-model:open="trialDrawer" width="600" :title="editingTrialId ? '编辑试验' : '新建试验'">
      <a-alert class="drawer-tip" type="warning" show-icon message="规则启用前必须人工确认" description="AI 解析或示例规则仅作为草案。" />
      <a-form layout="vertical">
        <a-form-item label="试验名称"><a-input v-model:value="trialForm.trial_name" /></a-form-item>
        <a-form-item label="注册号"><a-input v-model:value="trialForm.registration_no" /></a-form-item>
        <a-form-item label="PI"><a-input v-model:value="trialForm.pi" /></a-form-item>
        <a-form-item label="状态"><a-select v-model:value="trialForm.status" :options="statusOptions" /></a-form-item>
        <a-form-item label="入组规则 JSON"><a-textarea v-model:value="trialForm.inclusionText" :rows="4" /></a-form-item>
        <a-form-item label="排除规则 JSON"><a-textarea v-model:value="trialForm.exclusionText" :rows="4" /></a-form-item>
        <ActionBar>
          <a-button type="primary" :loading="saving" @click="saveTrial">保存</a-button>
          <a-button @click="fillDemoRules">填入示例</a-button>
          <a-button @click="trialDrawer = false">取消</a-button>
        </ActionBar>
      </a-form>
    </a-drawer>

    <!-- AI 解析弹窗 -->
    <a-modal v-model:open="parseOpen" title="AI 解析入排标准" width="640" @ok="parseCriteria">
      <a-form layout="vertical">
        <a-form-item label="入组标准原文"><a-textarea v-model:value="parseForm.inclusion_text" :rows="4" /></a-form-item>
        <a-form-item label="排除标准原文"><a-textarea v-model:value="parseForm.exclusion_text" :rows="4" /></a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, onBeforeUnmount } from 'vue'
import * as echarts from 'echarts/core'
import { FunnelChart } from 'echarts/charts'
import { TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import {
  Alert as AAlert, Button as AButton, Drawer as ADrawer, Form as AForm, FormItem as AFormItem,
  Input as AInput, Modal as AModal, Select as ASelect, Space as ASpace, Steps as ASteps,
  Table as ATable, Tag as ATag, Textarea as ATextarea /* message removed */ ,
} from 'ant-design-vue'
import { PageHeader, SectionHeader, MetricStrip, ActionBar, EmptyState } from '../components/common/design-system'
import { useClinicalTrial } from '../composables/useClinicalTrial'
import DataCompletenessRing from '../components/charts/risk/DataCompletenessRing.vue'

echarts.use([FunnelChart, TooltipComponent, CanvasRenderer])

const {
  loading, screening, saving, demoLoading,
  trials, candidates, lastScreenResult,
  trialDrawer, parseOpen, candidateOpen,
  selectedTrial, editingTrialId, selectedCandidate,
  trialForm, parseForm, statusOptions,
  scopeLabel, activeTrialCount, pendingCount,
  candidateEmptyText, screenDiagnosticText,
  openNewTrial, fillDemoRules, editTrial,
  statusLabel, openCandidate, ruleText,
  loadAll, saveTrial, removeTrial, createDemoTrial,
  activate, openParse, parseCriteria, screen, setCandidateStatus,
} = useClinicalTrial()

const currentStep = ref(0)
const selectedTrialId = ref('')

const stepItems = [
  { title: '选择试验' },
  { title: '候选患者' },
  { title: '状态跟踪' },
]

function nextStep() { if (currentStep.value < 2) currentStep.value++ }
function prevStep() { if (currentStep.value > 0) currentStep.value-- }

function selectTrial(trial: any) {
  selectedTrialId.value = trial.trial_id
  selectedTrial.value = trial
}

function statusTagColor(status: string) {
  const map: Record<string, string> = {
    pending: 'default', notified: 'blue', doctor_confirmed_suitable: 'green',
    doctor_confirmed_not_suitable: 'red', research_team_contacted: 'cyan',
    enrolled: 'green', not_enrolled: 'red',
  }
  return map[String(status || '').toLowerCase()] || 'default'
}

const kpiMetrics = computed(() => [
  { label: '试验总数', value: trials.value.length },
  { label: '招募中', value: activeTrialCount.value, variant: 'success' as const },
  { label: '候选患者', value: candidates.value.length, variant: 'info' as const },
  { label: '待确认', value: pendingCount.value, variant: 'warning' as const },
])

const candidateColumns = [
  { title: '患者', key: 'patient', width: 150 },
  { title: '匹配度', key: 'match_pct', width: 80 },
  { title: '满足条件', key: 'main_criteria', width: 240 },
  { title: '缺失数据', key: 'missing_count', width: 90 },
  { title: '排除风险', key: 'exclusion_risk', width: 120 },
  { title: '确认状态', key: 'status', width: 110 },
  { title: '操作', key: 'action', width: 70 },
]

const candidateRows = computed(() => candidates.value.map((c, idx) => ({ ...c, row_key: c.candidate_id || idx })))

// ── 筛选漏斗图 ──────────────────────────────────────────────────────
const funnelChartRef = ref<HTMLElement>()
let funnelChart: echarts.ECharts | null = null

const screeningCompleteness = computed(() => {
  const total = trials.value.length
  const active = activeTrialCount.value
  const withCandidates = candidates.value.length > 0 ? 1 : 0
  if (!total) return 0
  return Math.round(((active + withCandidates) / (total + 1)) * 100)
})

const funnelOption = computed(() => {
  const scanned = lastScreenResult.value?.scanned_patients || 0
  const candidatesCount = candidates.value.length
  const notified = candidates.value.filter((c: any) => c.status !== 'pending').length
  const enrolled = candidates.value.filter((c: any) => c.status === 'enrolled').length

  return {
    tooltip: { trigger: 'item', formatter: '{b}: {c}人' },
    series: [{
      type: 'funnel',
      left: '10%',
      width: '80%',
      sort: 'descending',
      gap: 4,
      label: { show: true, position: 'inside', fontSize: 12, color: '#fff' },
      data: [
        { value: scanned, name: '扫描患者', itemStyle: { color: '#2563EB' } },
        { value: candidatesCount, name: '候选匹配', itemStyle: { color: '#12B76A' } },
        { value: notified, name: '已通知', itemStyle: { color: '#F79009' } },
        { value: enrolled, name: '已入组', itemStyle: { color: '#7C3AED' } },
      ].filter(d => d.value > 0),
    }],
  }
})

function initFunnelChart() {
  if (!funnelChartRef.value) return
  funnelChart = echarts.init(funnelChartRef.value)
  funnelChart.setOption(funnelOption.value)
  const ro = new ResizeObserver(() => funnelChart?.resize())
  ro.observe(funnelChartRef.value)
}

onMounted(() => { setTimeout(initFunnelChart, 400) })
onBeforeUnmount(() => { funnelChart?.dispose(); funnelChart = null })
</script>

<style scoped>
.trial-page {
  padding: var(--page-padding, 24px);
  display: flex;
  flex-direction: column;
  gap: var(--section-gap, 24px);
  max-width: 1400px;
}

/* 筛选漏斗可视化 */
.trial-viz-row {
  display: grid;
  grid-template-columns: 1fr 200px;
  gap: 16px;
}

.trial-viz-card {
  background: var(--color-bg-surface, #fff);
  border: 1px solid var(--color-border, #E3E7EC);
  border-radius: var(--radius-lg, 8px);
  padding: 14px 16px;
}

.trial-viz-card h4 {
  margin: 0 0 8px;
  font-size: 13px;
  font-weight: 600;
  color: #1a1a1a;
}

.trial-viz-chart {
  width: 100%;
  height: 200px;
}

.trial-viz-card--ring {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

.trial-viz-ring-label {
  margin-top: 8px;
  font-size: 12px;
  color: #8c8c8c;
}
.step-card {
  background: var(--color-bg-surface, #fff);
  border: 1px solid var(--color-border, #E3E7EC);
  border-radius: var(--radius-lg, 8px);
  padding: var(--card-padding, 16px);
}
.step-panel {
  background: var(--color-bg-surface, #fff);
  border: 1px solid var(--color-border, #E3E7EC);
  border-radius: var(--radius-lg, 8px);
  padding: var(--card-padding, 16px);
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.trial-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 12px; }
.trial-card {
  padding: 14px; border: 1px solid var(--color-border, #E3E7EC);
  border-radius: var(--radius-lg, 8px); background: var(--color-bg-surface, #fff);
  display: flex; flex-direction: column; gap: 8px; cursor: pointer; transition: border-color 0.15s;
}
.trial-card:hover { border-color: var(--color-primary, #2563EB); }
.trial-card.selected { border-color: var(--color-primary, #2563EB); background: var(--color-primary-bg, rgba(37,99,235,0.04)); }
.trial-card-head { display: flex; justify-content: space-between; align-items: center; }
.trial-reg { font-size: 12px; color: var(--color-text-secondary, #667085); }
.trial-card h3 { margin: 0; font-size: var(--text-card-title, 14px); color: var(--color-text-primary, #18212B); }
.trial-card p { margin: 0; font-size: var(--text-caption, 12px); color: var(--color-text-secondary, #667085); }
.rule-summary { display: flex; gap: 12px; font-size: 12px; color: var(--color-text-secondary, #667085); }
.trial-actions { display: flex; gap: 6px; flex-wrap: wrap; }
.candidate-table-wrap { overflow-x: auto; }
.patient-cell { display: flex; align-items: center; gap: 8px; }
.bed-badge {
  padding: 2px 8px; border-radius: var(--radius-tag, 4px);
  background: var(--color-primary-bg, rgba(37,99,235,0.08));
  color: var(--color-primary, #2563EB); font-size: 12px; font-weight: var(--weight-semibold, 600);
  white-space: nowrap;
}
.match-pct { font-weight: var(--weight-bold, 700); color: var(--color-primary, #2563EB); }
.criteria-cell { display: flex; flex-wrap: wrap; gap: 4px; }
.criteria-tag {
  padding: 2px 6px; border-radius: var(--radius-tag, 4px);
  background: var(--color-success-bg, rgba(22,132,91,0.08));
  color: var(--color-success, #16845B); font-size: 11px;
  max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.exclusion-risk { font-size: 12px; color: var(--color-warning, #B54708); }
.muted { color: var(--color-text-secondary, #667085); font-size: 12px; }
.diagnostics-card {
  padding: 14px; border-radius: var(--radius-lg, 8px);
  background: var(--color-bg-surface-secondary, #F1F3F5);
  border: 1px solid var(--color-border, #E3E7EC);
}
.diag-row { display: flex; gap: 16px; align-items: center; font-size: 13px; }
.diag-row span { color: var(--color-text-secondary, #667085); }
.diag-row strong { color: var(--color-text-primary, #18212B); }
.diag-text { margin-top: 8px; font-size: 12px; color: var(--color-text-secondary, #667085); }
.scope-note {
  padding: 10px 14px; border-radius: var(--radius-md, 6px);
  background: var(--color-primary-bg, rgba(37,99,235,0.08));
  border: 1px solid rgba(37,99,235,0.16);
  color: var(--color-primary, #2563EB); font-size: 13px;
}
.match-detail { display: flex; flex-direction: column; gap: 16px; }
.match-header { display: flex; align-items: center; gap: 12px; }
.match-header h2 { margin: 0; font-size: var(--text-section-title, 16px); color: var(--color-text-primary, #18212B); }
.match-hint { margin: 0; font-size: var(--text-body, 14px); color: var(--color-text-secondary, #667085); }
.match-section h3 { margin: 0 0 8px; font-size: var(--text-card-title, 14px); color: var(--color-primary, #2563EB); }
.match-section p { margin: 0; font-size: var(--text-body, 14px); color: var(--color-text-primary, #18212B); }
.match-section ul { margin: 0; padding-left: 18px; }
.match-section li { font-size: var(--text-body, 14px); color: var(--color-text-primary, #18212B); line-height: 1.6; }
.status-flow { display: flex; flex-wrap: wrap; gap: 8px; }
.status-flow span {
  padding: 6px 10px; border-radius: var(--radius-tag, 4px);
  background: var(--color-bg-surface-secondary, #F1F3F5);
  border: 1px solid var(--color-border, #E3E7EC);
  font-size: 12px; color: var(--color-text-secondary, #667085);
}
.status-flow span.done {
  background: var(--color-success-bg, rgba(22,132,91,0.08));
  border-color: rgba(22,132,91,0.24);
  color: var(--color-success, #16845B);
}
.drawer-tip { margin-bottom: 12px; }
@media (max-width: 768px) {
  .trial-grid { grid-template-columns: 1fr; }
  .diag-row { flex-wrap: wrap; }
}
</style>
