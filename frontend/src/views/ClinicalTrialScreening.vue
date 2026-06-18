<template>
  <div class="trial-page">
    <section class="trial-hero">
      <div>
        <div class="eyebrow">Recruitment Safety Gate</div>
        <h1>临床试验筛选</h1>
        <p>维护结构化入排标准，自动扫描当前 ICU 患者，只提示“可能符合”，不自动入组。</p>
      </div>
      <a-space wrap>
        <a-button :loading="loading" @click="loadAll">刷新</a-button>
        <a-button type="primary" @click="openNewTrial">新建试验</a-button>
        <a-button :loading="screening" @click="screen">立即筛选</a-button>
      </a-space>
    </section>

    <section class="guide-rail">
      <article>
        <span>01</span>
        <strong>配置试验</strong>
        <p>录入试验名称、PI、状态和结构化入排规则。</p>
      </article>
      <article>
        <span>02</span>
        <strong>启用招募</strong>
        <p>只有“招募中”的试验会参与自动筛选。</p>
      </article>
      <article>
        <span>03</span>
        <strong>人工确认</strong>
        <p>候选患者必须由医生和研究团队确认，系统只提供依据。</p>
      </article>
    </section>

    <section class="kpi-grid">
      <article class="kpi-card">
        <span>试验总数</span>
        <strong>{{ trials.length }}</strong>
        <small>准备中 / 招募中 / 暂停 / 结束</small>
      </article>
      <article class="kpi-card kpi-card--green">
        <span>招募中</span>
        <strong>{{ activeTrialCount }}</strong>
        <small>会参与当前筛选</small>
      </article>
      <article class="kpi-card kpi-card--cyan">
        <span>候选患者</span>
        <strong>{{ candidates.length }}</strong>
        <small>仅表示可能符合</small>
      </article>
      <article class="kpi-card kpi-card--amber">
        <span>待确认</span>
        <strong>{{ pendingCount }}</strong>
        <small>需主管医生复核</small>
      </article>
    </section>

    <a-alert
      v-if="!trials.length && !loading"
      class="mb"
      type="info"
      show-icon
      message="当前还没有临床试验配置"
      description="请先新建试验并设置入排规则。也可以点击“一键创建示例试验并筛选”，快速生成一个肺炎/脓毒症观察性研究示例。"
    />

    <section class="layout">
      <a-card class="panel" :bordered="false">
        <template #title>临床试验列表</template>
        <template #extra>
          <a-space>
            <a-button size="small" @click="createDemoTrial" :loading="demoLoading">演示模板</a-button>
            <a-button size="small" type="primary" @click="openNewTrial">新建</a-button>
          </a-space>
        </template>

        <div v-if="!trials.length && !loading" class="empty-state">
          <div class="empty-badge">Trial</div>
          <h2>筛选器还没有可扫描的试验</h2>
          <p>建议从一个简单、可解释的结构化规则开始，例如：年龄 ≥18 岁，诊断包含“肺炎”或“脓毒症”。</p>
          <a-space wrap>
            <a-button type="primary" @click="createDemoTrial" :loading="demoLoading">创建示例试验并筛选</a-button>
            <a-button @click="openNewTrial">手动新建试验</a-button>
          </a-space>
        </div>

        <div v-else class="trial-list">
          <article v-for="trial in trials" :key="trial.trial_id" class="trial-card">
            <div class="trial-card-head">
              <a-tag :color="trial.status === '招募中' ? 'green' : 'gold'">{{ trial.status || '准备中' }}</a-tag>
              <span>{{ trial.registration_no || '未登记注册号' }}</span>
            </div>
            <h3>{{ trial.trial_name }}</h3>
            <p>PI：{{ trial.pi || '未指定' }} · {{ trial.study_type || '研究类型待补充' }}</p>
            <div class="rule-summary">
              <span>入组 {{ trial.inclusion_rules?.length || 0 }} 条</span>
              <span>排除 {{ trial.exclusion_rules?.length || 0 }} 条</span>
            </div>
            <a-space wrap>
              <a-button size="small" type="primary" ghost @click="activate(trial)">启用招募</a-button>
              <a-button size="small" @click="openParse(trial)">系统解析标准</a-button>
              <a-button size="small" @click="editTrial(trial)">编辑</a-button>
              <a-button size="small" danger ghost @click="removeTrial(trial)">删除</a-button>
            </a-space>
          </article>
        </div>
      </a-card>

      <a-card class="panel" :bordered="false">
        <template #title>候选患者</template>
        <template #extra>
          <span class="panel-hint">点击卡片查看匹配依据</span>
        </template>

        <div v-if="!candidates.length && !loading" class="empty-state">
          <div class="empty-badge">Match</div>
          <h2>暂未产生候选患者</h2>
          <p>{{ candidateEmptyText }}</p>
          <div class="scope-note">当前筛选范围：{{ scopeLabel }}</div>
          <div v-if="lastScreenResult" class="screen-diagnostics">
            <strong>最近一次筛选</strong>
            <span>扫描试验 {{ lastScreenResult.scanned_trials || 0 }} 个，患者 {{ lastScreenResult.scanned_patients || 0 }} 人，候选 {{ lastScreenResult.candidates?.length || 0 }} 人</span>
            <span v-if="screenDiagnosticText">{{ screenDiagnosticText }}</span>
          </div>
          <a-space wrap>
            <a-button :disabled="!activeTrialCount" :loading="screening" type="primary" @click="screen">立即筛选</a-button>
            <a-button v-if="!trials.length" @click="createDemoTrial" :loading="demoLoading">创建示例试验</a-button>
          </a-space>
        </div>

        <div v-else class="candidate-list">
          <article v-for="candidate in candidates" :key="candidate.candidate_id" class="candidate-card" @click="openCandidate(candidate)">
            <div class="candidate-main">
              <div class="bed-pill">{{ candidate.bed_no || '--' }}床</div>
              <div>
                <h3>{{ candidate.patient_name || '脱敏患者' }}</h3>
                <p>{{ candidate.trial_name }}</p>
                <div class="candidate-diagnosis">{{ candidate.diagnosis_summary || '暂无诊断摘要' }}</div>
              </div>
            </div>
            <div class="candidate-meta">
              <a-tag color="blue">{{ statusLabel(candidate.status) }}</a-tag>
              <strong>{{ Math.round((candidate.match_evidence?.confidence || 0) * 100) }}%</strong>
            </div>
          </article>
        </div>
      </a-card>
    </section>

    <a-drawer v-model:open="trialDrawer" width="680" title="新建临床试验">
      <a-alert
        class="mb"
        type="warning"
        show-icon
        message="规则启用前必须人工确认"
        description="系统解析或示例规则仅作为草案，研究人员确认后才能用于正式招募提醒。"
      />
      <a-form layout="vertical">
        <a-form-item label="试验名称"><a-input v-model:value="trialForm.trial_name" /></a-form-item>
        <a-form-item label="注册号"><a-input v-model:value="trialForm.registration_no" /></a-form-item>
        <a-form-item label="PI"><a-input v-model:value="trialForm.pi" /></a-form-item>
        <a-form-item label="状态"><a-select v-model:value="trialForm.status" :options="statusOptions" /></a-form-item>
        <a-form-item label="结构化入组规则 JSON">
          <a-textarea v-model:value="trialForm.inclusionText" :rows="5" />
        </a-form-item>
        <a-form-item label="结构化排除规则 JSON">
          <a-textarea v-model:value="trialForm.exclusionText" :rows="5" />
        </a-form-item>
        <a-space>
          <a-button type="primary" :loading="saving" @click="saveTrial">保存</a-button>
          <a-button @click="fillDemoRules">填入示例规则</a-button>
        </a-space>
      </a-form>
    </a-drawer>

    <a-modal v-model:open="parseOpen" title="系统解析入排标准草案" width="760" @ok="parseCriteria">
      <a-form layout="vertical">
        <a-form-item label="入组标准原文"><a-textarea v-model:value="parseForm.inclusion_text" :rows="5" /></a-form-item>
        <a-form-item label="排除标准原文"><a-textarea v-model:value="parseForm.exclusion_text" :rows="5" /></a-form-item>
      </a-form>
    </a-modal>

    <a-drawer v-model:open="candidateOpen" width="760" title="匹配详情">
      <div v-if="selectedCandidate" class="match-detail">
        <h2>{{ selectedCandidate.message || '该患者可能符合临床试验入组标准，请人工确认。' }}</h2>
        <section class="diagnosis-evidence">
          <h3>系统抓取到的诊断</h3>
          <p>{{ selectedCandidate.diagnosis_summary || '暂无诊断摘要，不能仅凭年龄等非诊断项判断入组。' }}</p>
        </section>
        <section>
          <h3>状态流转</h3>
          <div class="status-flow">
            <span
              v-for="step in selectedCandidate.status_flow || []"
              :key="step.status"
              :class="{ done: step.done }"
            >
              {{ step.label }}
            </span>
          </div>
        </section>
        <section>
          <h3>满足的入组标准</h3>
          <p v-if="!selectedCandidate.match_evidence?.matched_inclusion?.length">暂无明确入组证据</p>
          <ul>
            <li v-for="(item, idx) in selectedCandidate.match_evidence?.matched_inclusion || []" :key="idx">
              {{ ruleText(item) }}
            </li>
          </ul>
        </section>
        <section>
          <h3>缺失但需确认的数据</h3>
          <p v-if="!selectedCandidate.match_evidence?.missing_data?.length">未发现关键缺失项</p>
          <ul>
            <li v-for="(item, idx) in selectedCandidate.match_evidence?.missing_data || []" :key="idx">
              {{ item.reason || JSON.stringify(item.rule || item) }}
            </li>
          </ul>
        </section>
        <section>
          <h3>未触发的排除标准</h3>
          <p v-if="!selectedCandidate.match_evidence?.untriggered_exclusion?.length">暂无排除规则或无可展示证据</p>
          <ul>
            <li v-for="(item, idx) in selectedCandidate.match_evidence?.untriggered_exclusion || []" :key="idx">
              {{ ruleText(item) }}
            </li>
          </ul>
        </section>
        <a-alert
          type="warning"
          show-icon
          message="仅提示可能符合，不自动入组"
          :description="selectedCandidate.match_evidence?.safety_notice || '必须由主管医生和研究团队人工确认。'"
        />
        <a-space wrap>
          <a-button @click="setCandidateStatus('notified')">已通知主管医生</a-button>
          <a-button type="primary" @click="setCandidateStatus('doctor_confirmed_suitable')">医生确认适合</a-button>
          <a-button @click="setCandidateStatus('research_team_contacted')">已联系研究团队</a-button>
          <a-button type="primary" ghost @click="setCandidateStatus('enrolled')">已入组</a-button>
          <a-button danger @click="setCandidateStatus('doctor_confirmed_not_suitable')">医生确认不适合</a-button>
          <a-button danger ghost @click="setCandidateStatus('not_enrolled')">不入组</a-button>
        </a-space>
      </div>
    </a-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import {
  Alert as AAlert,
  Button as AButton,
  Card as ACard,
  Drawer as ADrawer,
  Form as AForm,
  FormItem as AFormItem,
  Input as AInput,
  Modal as AModal,
  Select as ASelect,
  Space as ASpace,
  Tag as ATag,
  Textarea as ATextarea,
  message,
} from 'ant-design-vue'
import { deleteClinicalTrial, getClinicalTrials, getTrialCandidates, postActivateTrial, postCandidateStatus, postClinicalTrial, postParseCriteria, postScreenTrials, putClinicalTrial, type ClinicalTrialScopeParams } from '../api/clinicalTrials'

const route = useRoute()
const loading = ref(false)
const screening = ref(false)
const saving = ref(false)
const demoLoading = ref(false)
const trials = ref<any[]>([])
const candidates = ref<any[]>([])
const trialDrawer = ref(false)
const parseOpen = ref(false)
const candidateOpen = ref(false)
const selectedTrial = ref<any>(null)
const editingTrialId = ref('')
const selectedCandidate = ref<any>(null)
const lastScreenResult = ref<any>(null)
const trialForm = reactive<any>({ trial_name: '', registration_no: '', pi: '', status: '准备中', inclusionText: '[]', exclusionText: '[]' })
const parseForm = reactive<any>({
  inclusion_text: '年龄 ≥18 岁；ICU 在科；诊断包含重症肺炎、脓毒症或感染性休克。',
  exclusion_text: '年龄 <18 岁；已明确拒绝研究；临终照护或治疗限制。',
})
const statusOptions = ['准备中', '招募中', '暂停', '结束'].map((value) => ({ value, label: value }))
const routeDeptCode = computed(() => String(route.query.dept_code || route.query.deptCode || '').trim())
const routeDeptName = computed(() => String(route.query.dept || route.query.department || '').trim())
const scopeLabel = computed(() => routeDeptName.value || routeDeptCode.value || '全部 ICU 在科患者')

const activeTrialCount = computed(() => trials.value.filter((trial) => trial.status === '招募中').length)
const pendingCount = computed(() => candidates.value.filter((item) => item.status === 'pending').length)
const candidateEmptyText = computed(() => {
  if (!trials.value.length) return '当前没有试验配置，因此无法筛选候选患者。'
  if (!activeTrialCount.value) return '已有试验但尚未启用招募，请先点击“启用招募”。'
  return '已扫描但未发现满足条件且未触发排除标准的患者，可查看规则是否过严或数据是否缺失。'
})
const screenDiagnosticText = computed(() => {
  const diagnostics = Array.isArray(lastScreenResult.value?.diagnostics) ? lastScreenResult.value.diagnostics : []
  const first = diagnostics.find((item: any) => item?.trial_name) || diagnostics[0]
  if (!first) return ''
  if (first.matched > 0) return `${first.trial_name || '当前试验'}已有 ${first.matched} 名患者进入候选，列表刷新后可查看。`
  const parts = []
  if (first.unmet) parts.push(`${first.unmet} 人未满足入组规则`)
  if (first.missing_only) parts.push(`${first.missing_only} 人仅缺少确认数据`)
  if (first.excluded) parts.push(`${first.excluded} 人触发排除标准`)
  return parts.length ? `${first.trial_name || '当前试验'}：${parts.join('，')}。` : ''
})
function requestParams(): ClinicalTrialScopeParams {
  const params: ClinicalTrialScopeParams = { patient_scope: 'in_dept' }
  if (routeDeptCode.value) params.dept_code = routeDeptCode.value
  else if (routeDeptName.value) params.dept = routeDeptName.value
  return params
}

function demoRules() {
  return {
    inclusion: [
      { field: 'age', operator: 'gte', value: 18, source_text: '年龄 ≥18 岁' },
      { field: 'diagnosis', operator: 'regex', value: '肺炎|脓毒|感染|ARDS|呼吸衰竭', source_text: '诊断包含肺炎/脓毒症/ARDS/呼吸衰竭' },
    ],
    exclusion: [
      { field: 'age', operator: 'lt', value: 18, source_text: '年龄 <18 岁' },
    ],
  }
}
function resetForm() {
  Object.assign(trialForm, { trial_name: '', registration_no: '', pi: '', status: '准备中', inclusionText: '[]', exclusionText: '[]' })
  editingTrialId.value = ''
}
function openNewTrial() {
  resetForm()
  trialDrawer.value = true
}
function fillDemoRules() {
  const rules = demoRules()
  trialForm.inclusionText = JSON.stringify(rules.inclusion, null, 2)
  trialForm.exclusionText = JSON.stringify(rules.exclusion, null, 2)
}
function editTrial(row: any) {
  editingTrialId.value = row.trial_id
  Object.assign(trialForm, {
    trial_name: row.trial_name || '',
    registration_no: row.registration_no || '',
    pi: row.pi || '',
    status: row.status || '准备中',
    inclusionText: JSON.stringify(row.inclusion_rules || [], null, 2),
    exclusionText: JSON.stringify(row.exclusion_rules || [], null, 2),
  })
  trialDrawer.value = true
}
function statusLabel(v: string) {
  return ({ pending: '待确认', notified: '已通知', doctor_confirmed_suitable: '医生确认适合', doctor_confirmed_not_suitable: '医生确认不适合', research_team_contacted: '已联系研究团队', enrolled: '已入组', not_enrolled: '不入组' } as any)[v] || v
}
function parseJson(text: string) {
  try {
    const v = JSON.parse(text || '[]')
    return Array.isArray(v) ? v : []
  } catch {
    message.warning('规则 JSON 格式不正确，请检查后再保存')
    return []
  }
}
function openCandidate(record: any) {
  selectedCandidate.value = record
  candidateOpen.value = true
}
function ruleText(item: any) {
  const rule = item.rule || {}
  return `${rule.source_text || rule.field || '规则'}：${item.evidence || item.actual || ''}`
}

async function loadAll() {
  loading.value = true
  try {
    const [t, c] = await Promise.all([getClinicalTrials(), getTrialCandidates(requestParams())])
    trials.value = t.data?.trials || []
    candidates.value = c.data?.candidates || []
  } finally {
    loading.value = false
  }
}
async function saveTrial() {
  if (!trialForm.trial_name?.trim()) {
    message.warning('请填写试验名称')
    return
  }
  saving.value = true
  try {
    const payload = { ...trialForm, inclusion_rules: parseJson(trialForm.inclusionText), exclusion_rules: parseJson(trialForm.exclusionText) }
    if (editingTrialId.value) await putClinicalTrial(editingTrialId.value, payload)
    else await postClinicalTrial(payload)
    message.success(editingTrialId.value ? '试验已更新' : '试验已保存')
    trialDrawer.value = false
    editingTrialId.value = ''
    await loadAll()
  } finally {
    saving.value = false
  }
}
function removeTrial(row: any) {
  AModal.confirm({
    title: '删除临床试验配置',
    content: `确认删除“${row.trial_name || '未命名试验'}”？候选记录不会自动入组，删除后该试验不再参与筛选。`,
    okText: '删除',
    okType: 'danger',
    cancelText: '取消',
    async onOk() {
      await deleteClinicalTrial(row.trial_id)
      message.success('试验已删除')
      await loadAll()
    },
  })
}
async function createDemoTrial() {
  demoLoading.value = true
  try {
    const rules = demoRules()
    const res = await postClinicalTrial({
      trial_name: '重症肺炎/脓毒症 ICU 观察性队列研究（示例）',
      registration_no: 'DEMO-ICU-SEPSIS-PNEUMONIA',
      pi: '示例 PI',
      department: 'ICU',
      study_type: '前瞻性观察 / 回顾性队列',
      status: '招募中',
      inclusion_rules: rules.inclusion,
      exclusion_rules: rules.exclusion,
      remarks: '示例试验用于演示规则筛选流程，请按真实伦理批件和方案修改后再用于正式提醒。',
    })
    const trialId = res.data?.trial?.trial_id
    if (trialId) await postActivateTrial(trialId)
    await postScreenTrials(requestParams())
    message.success('已创建示例试验并完成一次筛选')
    await loadAll()
  } finally {
    demoLoading.value = false
  }
}
async function activate(row: any) {
  await postActivateTrial(row.trial_id)
  message.success('试验已启用招募')
  await loadAll()
}
function openParse(row: any) {
  selectedTrial.value = row
  parseOpen.value = true
}
async function parseCriteria() {
  if (!selectedTrial.value) return
  await postParseCriteria(selectedTrial.value.trial_id, parseForm)
  message.success('解析草案已保存，需人工确认后启用')
}
async function screen() {
  screening.value = true
  try {
    const res = await postScreenTrials(requestParams())
    lastScreenResult.value = res.data || null
    const count = res.data?.candidates?.length || 0
    const scannedPatients = res.data?.scanned_patients ?? 0
    const scannedTrials = res.data?.scanned_trials ?? 0
    if (count > 0) {
      message.success(`筛选完成：扫描 ${scannedTrials} 个试验 / ${scannedPatients} 名患者，候选 ${count} 人`)
    } else {
      message.warning(`筛选完成但暂无候选：扫描 ${scannedTrials} 个试验 / ${scannedPatients} 名患者`)
    }
    await loadAll()
  } finally {
    screening.value = false
  }
}
async function setCandidateStatus(status: string) {
  if (!selectedCandidate.value) return
  await postCandidateStatus(selectedCandidate.value.candidate_id, { status })
  message.success('候选状态已更新')
  await loadAll()
}
watch(() => [route.query.deptCode, route.query.dept_code, route.query.dept, route.query.department], () => {
  void loadAll()
})

onMounted(loadAll)
</script>

<style scoped>
.trial-page {
  min-height: calc(100vh - 76px);
  padding: 20px;
  color: var(--text-main);
  background: #FFFFFF;
}
.trial-hero {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 18px;
  padding: 18px;
  border: 1px solid rgba(80,199,255,.16);
  border-radius: 18px;
  background: #FFFFFF;
}
.eyebrow {
  color: #67e8f9;
  font-weight: 900;
  letter-spacing: .12em;
  font-size: 12px;
  text-transform: uppercase;
}
h1, h2, h3, p { margin: 0; }
h1 { margin-top: 4px; color: #f0fbff; font-size: 28px; }
.trial-hero p { margin-top: 8px; color: #9fc4d7; }
.guide-rail, .kpi-grid, .layout {
  display: grid;
  gap: 12px;
}
.guide-rail {
  grid-template-columns: repeat(3, minmax(0, 1fr));
  margin: 14px 0;
}
.guide-rail article, .kpi-card, .trial-card, .candidate-card {
  border: 1px solid rgba(125,167,214,.14);
  border-radius: 4px;
  background: rgba(7, 20, 34, .72);
}
.guide-rail article { padding: 14px; display: grid; gap: 6px; }
.guide-rail span { color: #22d3ee; font-weight: 900; }
.guide-rail strong, .trial-card h3, .candidate-card h3 { color: #f0fbff; }
.guide-rail p, .trial-card p, .candidate-card p, .empty-state p, .match-detail p, .match-detail li, .candidate-diagnosis { color: #b7cfe0; }
.kpi-grid {
  grid-template-columns: repeat(4, minmax(0, 1fr));
  margin-bottom: 14px;
}
.kpi-card { padding: 14px; }
.kpi-card span, .kpi-card small { display: block; color: #8aa4b8; }
.kpi-card strong { display: block; margin: 5px 0; color: #f2fbff; font-size: 30px; line-height: 1; }
.kpi-card--green { background: #FFFFFF; }
.kpi-card--cyan { background: #FFFFFF; }
.kpi-card--amber { background: #FFFFFF; }
.layout { grid-template-columns: minmax(0, 1.05fr) minmax(420px, .95fr); }
.panel { background: rgba(10,25,42,.92); border-radius: 4px; }
.panel-hint, .trial-card span, .rule-summary, .candidate-meta { color: #88a2b4; }
.empty-state {
  display: grid;
  place-items: center;
  gap: 12px;
  min-height: 320px;
  text-align: center;
  border: 1px dashed rgba(103,232,249,.24);
  border-radius: 4px;
  background: rgba(2,8,20,.22);
}
.empty-badge {
  width: 74px;
  height: 74px;
  display: grid;
  place-items: center;
  border-radius: 24px;
  color: #67e8f9;
  font-weight: 900;
  background: rgba(34,211,238,.1);
  border: 1px solid rgba(103,232,249,.2);
}
.empty-state p { max-width: 520px; }
.screen-diagnostics {
  display: grid;
  gap: 4px;
  max-width: 560px;
  padding: 10px 12px;
  border-radius: 4px;
  border: 1px solid rgba(103,232,249,.2);
  background: rgba(8, 47, 73, .28);
  color: #4E5969;
  font-size: 12px;
  line-height: 1.55;
}
.screen-diagnostics strong {
  color: #67e8f9;
  font-size: 12px;
}
.scope-note {
  padding: 8px 12px;
  border-radius: 999px;
  border: 1px solid rgba(103,232,249,.18);
  background: rgba(8, 47, 73, .24);
  color: #4E5969;
  font-size: 12px;
}
.trial-list, .candidate-list { display: grid; gap: 10px; }
.trial-card, .candidate-card {
  padding: 13px;
  display: grid;
  gap: 10px;
}
.trial-card-head, .candidate-main, .candidate-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}
.rule-summary { display: flex; gap: 12px; }
.candidate-card { cursor: pointer; transition: transform .15s ease, border-color .15s ease; }
.candidate-card:hover { transform: translateY(-1px); border-color: rgba(103,232,249,.36); }
.candidate-main { justify-content: flex-start; }
.bed-pill {
  display: grid;
  place-items: center;
  min-width: 58px;
  height: 42px;
  border-radius: 4px;
  color: #ecfeff;
  font-weight: 900;
  background: rgba(14, 116, 144, .35);
  border: 1px solid rgba(103,232,249,.18);
}
.candidate-meta strong { color: #67e8f9; font-size: 20px; }
.candidate-diagnosis {
  display: -webkit-box;
  margin-top: 6px;
  max-width: 560px;
  overflow: hidden;
  font-size: 12px;
  line-height: 1.45;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}
.match-detail { display: grid; gap: 16px; }
.match-detail h2 { color: #f0fbff; font-size: 18px; }
.match-detail h3 { color: #67e8f9; font-size: 14px; }
.match-detail ul { margin: 8px 0 0; padding-left: 18px; }
.diagnosis-evidence {
  padding: 12px;
  border: 1px solid rgba(103,232,249,.18);
  border-radius: 4px;
  background: rgba(8, 47, 73, .24);
}
.status-flow {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.status-flow span {
  padding: 7px 10px;
  border-radius: 999px;
  color: #88a2b4;
  background: rgba(2,8,20,.28);
  border: 1px solid rgba(125,167,214,.14);
}
.status-flow span.done {
  color: #dcfce7;
  background: rgba(22,101,52,.35);
  border-color: rgba(74,222,128,.25);
}
.mb { margin-bottom: 12px; }
html[data-theme='light'] .trial-page {
  color: #10243d;
  background: #FFFFFF;
}
html[data-theme='light'] .trial-hero,
html[data-theme='light'] .panel,
html[data-theme='light'] .guide-rail article,
html[data-theme='light'] .kpi-card,
html[data-theme='light'] .trial-card,
html[data-theme='light'] .candidate-card,
html[data-theme='light'] .empty-state,
html[data-theme='light'] .screen-diagnostics,
html[data-theme='light'] .scope-note,
html[data-theme='light'] .status-flow span {
  border-color: rgba(203, 213, 225, .82);
  background: #FFFFFF;
  box-shadow: 0 8px 22px rgba(15, 23, 42, .05);
}
html[data-theme='light'] .kpi-card--green {
  border-color: rgba(16, 185, 129, .24);
  background: #FFFFFF;
}
html[data-theme='light'] .kpi-card--cyan {
  border-color: rgba(14, 165, 233, .24);
  background: #FFFFFF;
}
html[data-theme='light'] .kpi-card--amber {
  border-color: rgba(245, 158, 11, .26);
  background: #FFFFFF;
}
html[data-theme='light'] h1,
html[data-theme='light'] .guide-rail strong,
html[data-theme='light'] .trial-card h3,
html[data-theme='light'] .candidate-card h3,
html[data-theme='light'] .kpi-card strong,
html[data-theme='light'] .empty-state h2,
html[data-theme='light'] .match-detail h2 {
  color: #12314f;
}
html[data-theme='light'] .trial-hero p,
html[data-theme='light'] .guide-rail p,
html[data-theme='light'] .trial-card p,
html[data-theme='light'] .candidate-card p,
html[data-theme='light'] .candidate-diagnosis,
html[data-theme='light'] .empty-state p,
html[data-theme='light'] .match-detail p,
html[data-theme='light'] .match-detail li,
html[data-theme='light'] .panel-hint,
html[data-theme='light'] .trial-card span,
html[data-theme='light'] .rule-summary,
html[data-theme='light'] .candidate-meta,
html[data-theme='light'] .kpi-card span,
html[data-theme='light'] .kpi-card small,
html[data-theme='light'] .screen-diagnostics,
html[data-theme='light'] .scope-note,
html[data-theme='light'] .status-flow span {
  color: #4E5969;
}
html[data-theme='light'] .eyebrow,
html[data-theme='light'] .guide-rail span,
html[data-theme='light'] .screen-diagnostics strong,
html[data-theme='light'] .match-detail h3,
html[data-theme='light'] .candidate-meta strong {
  color: #0369a1;
}
html[data-theme='light'] .empty-badge,
html[data-theme='light'] .bed-pill {
  border-color: rgba(14, 165, 233, .24);
  background: rgba(240, 249, 255, .98);
  color: #0369a1;
}
html[data-theme='light'] .candidate-card:hover {
  border-color: rgba(14, 165, 233, .38);
  background: #FFFFFF;
  box-shadow: inset 3px 0 0 rgba(14, 165, 233, .68), 0 8px 20px rgba(14, 165, 233, .08);
}
html[data-theme='light'] .status-flow span.done {
  color: #047857;
  border-color: rgba(16, 185, 129, .24);
  background: rgba(236, 253, 245, .98);
}
html[data-theme='light'] .trial-page :deep(.ant-card-head) {
  border-bottom-color: rgba(203, 213, 225, .82);
}
html[data-theme='light'] .trial-page :deep(.ant-card-head-title) {
  color: #12314f;
  font-weight: 800;
}
html[data-theme='light'] .diagnosis-evidence {
  border-color: rgba(14, 165, 233, .18);
  background: #FFFFFF;
}
html[data-theme='light'] .trial-page :deep(.ant-input),
html[data-theme='light'] .trial-page :deep(.ant-select-selector),
html[data-theme='light'] .trial-page :deep(.ant-input-affix-wrapper),
html[data-theme='light'] .trial-page :deep(textarea.ant-input) {
  border-color: rgba(203, 213, 225, .92) !important;
  background: rgba(248, 250, 252, .98) !important;
  color: #1D2129 !important;
}
@media (max-width: 1280px) {
  .guide-rail, .kpi-grid, .layout { grid-template-columns: 1fr 1fr; }
}
@media (max-width: 760px) {
  .trial-page { padding: 12px; }
  .trial-hero { flex-direction: column; }
  .guide-rail, .kpi-grid, .layout { grid-template-columns: 1fr; }
}
</style>
