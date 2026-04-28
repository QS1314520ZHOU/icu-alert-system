<template>
  <div class="research-page">
    <section class="research-hero">
      <div>
        <div class="eyebrow">科研秘书 / PI 工作台</div>
        <h1>科室学术科研支撑</h1>
        <p>从“临床问题发现”到“课题立项、数据质量评估、OMOP 脱敏导出”的一站式科研入口。</p>
      </div>
      <a-space wrap>
        <a-button :loading="loading" @click="loadAll">刷新数据</a-button>
        <a-button type="primary" :loading="topicLoading" @click="generateTopics">AI 生成课题建议</a-button>
        <a-button :loading="omopLoading" @click="exportOmop">导出 OMOP 数据包</a-button>
      </a-space>
    </section>

    <section class="guide-rail">
      <article v-for="step in guideSteps" :key="step.title" class="guide-card">
        <span>{{ step.index }}</span>
        <strong>{{ step.title }}</strong>
        <p>{{ step.desc }}</p>
      </article>
    </section>

    <section class="kpi-grid">
      <article class="kpi-card">
        <span>在管科研项目</span>
        <strong>{{ portfolio.active_count ?? projects.length }}</strong>
        <small>论文 / 课题 / 基金 / 伦理</small>
      </article>
      <article class="kpi-card kpi-card--cyan">
        <span>AI 潜在课题</span>
        <strong>{{ topics.length }}</strong>
        <small>{{ topicSourceLabel }}</small>
      </article>
      <article class="kpi-card kpi-card--amber">
        <span>数据仓患者数</span>
        <strong>{{ quality.patient_count || 0 }}</strong>
        <small>默认脱敏统计</small>
      </article>
      <article class="kpi-card kpi-card--rose">
        <span>时间逻辑错误</span>
        <strong>{{ quality.time_logic_errors?.length || 0 }}</strong>
        <small>导出前建议治理</small>
      </article>
    </section>

    <section class="dashboard-grid">
      <a-card class="panel project-panel" :bordered="false">
        <template #title>科研项目看板</template>
        <template #extra><a-button size="small" type="primary" @click="openProjectDrawer()">新建项目</a-button></template>

        <div v-if="!projects.length && !loading" class="empty-project">
          <div class="empty-icon">立项</div>
          <h2>还没有科研项目</h2>
          <p>可以先从 AI 课题推荐中选择一个方向一键转为项目，或手动录入论文、基金、伦理和临床研究。</p>
          <a-space wrap>
            <a-button type="primary" @click="openProjectDrawer()">手动新建立项</a-button>
            <a-button :loading="topicLoading" @click="generateTopics">先生成课题建议</a-button>
          </a-space>
        </div>

        <div v-else class="project-list">
          <article v-for="project in projects" :key="project.project_id" class="project-card">
            <div class="project-head">
              <a-tag color="geekblue">{{ project.type || '课题' }}</a-tag>
              <a-tag :color="statusColor(project.status)">{{ project.status || '计划中' }}</a-tag>
            </div>
            <h3>{{ project.title }}</h3>
            <p>负责人：{{ project.owner || '未指定' }}</p>
            <small>{{ project.journal_or_funding_source || project.remarks || '暂无备注' }}</small>
          </article>
        </div>
      </a-card>

      <a-card class="panel quality-panel" :bordered="false">
        <template #title>数据质量与 OMOP 导出准备</template>
        <div class="quality-summary">
          <article>
            <span>缺失字段</span>
            <strong>{{ missingRows.length }}</strong>
          </article>
          <article>
            <span>异常值</span>
            <strong>{{ quality.outliers?.length || 0 }}</strong>
          </article>
          <article>
            <span>单位问题</span>
            <strong>{{ quality.unit_inconsistencies?.length || 0 }}</strong>
          </article>
        </div>
        <div class="quality-table">
          <div class="quality-row quality-row--head">
            <span>字段</span>
            <span>缺失率</span>
          </div>
          <div v-for="row in missingRows.slice(0, 8)" :key="row.field" class="quality-row">
            <span>{{ fieldLabel(row.field) }}</span>
            <span>{{ row.rate }}</span>
          </div>
          <div v-if="!missingRows.length" class="soft-empty">当前未发现明显字段缺失。</div>
        </div>
        <div class="omop-note">
          <strong>导出说明</strong>
          <p>OMOP CDM 导出默认脱敏，当前提供 PERSON、VISIT、CONDITION、DRUG、MEASUREMENT、PROCEDURE、OBSERVATION 最小表集。</p>
        </div>
        <div class="governance-list">
          <div class="section-title">数据治理建议</div>
          <article v-for="item in governance" :key="item.title" class="governance-card">
            <a-tag :color="item.priority === 'high' ? 'red' : item.priority === 'medium' ? 'gold' : 'green'">
              {{ item.priority === 'high' ? '优先' : item.priority === 'medium' ? '建议' : '通过' }}
            </a-tag>
            <div>
              <strong>{{ item.title }}</strong>
              <p>{{ item.detail }}</p>
            </div>
          </article>
        </div>
      </a-card>
    </section>

    <section class="portfolio-grid">
      <a-card class="panel" :bordered="false" title="项目组合分布">
        <div class="distribution-grid">
          <article v-for="row in statusRows" :key="row.key">
            <span>{{ row.key }}</span>
            <strong>{{ row.value }}</strong>
          </article>
        </div>
      </a-card>
      <a-card class="panel" :bordered="false" title="近期里程碑">
        <div v-if="!milestones.length" class="soft-empty">暂无里程碑。建议为项目补充伦理递交、数据锁库、统计分析、投稿等节点。</div>
        <div v-else class="milestone-list">
          <article v-for="item in milestones" :key="`${item.project_id}-${item.title}-${item.date}`">
            <strong>{{ item.title }}</strong>
            <span>{{ item.project_title }}</span>
            <small>{{ item.date || '未设置日期' }} · {{ item.status }}</small>
          </article>
        </div>
      </a-card>
    </section>

    <a-card class="panel topic-panel" :bordered="false">
      <template #title>AI 潜在课题推荐</template>
      <template #extra>
        <span class="panel-hint">基于数据摘要生成，需要 PI 人工确认</span>
      </template>
      <a-empty v-if="!topics.length" description="暂无课题建议。点击“AI 生成课题建议”开始发现选题。" />
      <div v-else class="topic-grid">
        <article v-for="topic in topics" :key="topic.suggestion_id || topic.title" class="topic-card">
          <div class="topic-head">
            <div class="topic-tags">
              <a-tag color="cyan">{{ topic.study_design || '研究设计待定' }}</a-tag>
              <a-tag :color="scoreColor(topic.feasibility_score)">可行性 {{ topic.feasibility_score || '—' }}</a-tag>
            </div>
            <a-button class="topic-action" size="small" type="primary" ghost @click="createProjectFromTopic(topic)">转为项目</a-button>
          </div>
          <h3>{{ localizeTitle(topic.title) }}</h3>
          <p>{{ localizeQuestion(topic.clinical_question) }}</p>
          <div class="evidence-box">
            <strong>数据依据</strong>
            <span>{{ localizeText(topic.data_basis) }}</span>
          </div>
          <dl>
            <div>
              <dt>主要结局</dt>
              <dd>{{ topic.primary_outcome || '待 PI 确认' }}</dd>
            </div>
            <div>
              <dt>伦理风险</dt>
              <dd>{{ topic.ethical_risk || '需伦理秘书评估' }}</dd>
            </div>
          </dl>
          <div class="topic-foot">
            <span>{{ topic.multi_center_potential ? '适合多中心协作' : '单中心优先' }}</span>
            <span>{{ confidenceLabel(topic.confidence) }}</span>
          </div>
        </article>
      </div>
    </a-card>

    <a-drawer v-model:open="drawerOpen" width="620" title="新建科研项目">
      <a-alert
        class="drawer-tip"
        type="info"
        show-icon
        message="建议先填写最小信息，后续再补充伦理号、附件、里程碑和统计方案。"
      />
      <a-form layout="vertical">
        <a-form-item label="项目标题"><a-input v-model:value="form.title" placeholder="例如：ARDS 俯卧位治疗质量改进研究" /></a-form-item>
        <a-form-item label="项目类型"><a-select v-model:value="form.type" :options="typeOptions" /></a-form-item>
        <a-form-item label="负责人 / PI"><a-input v-model:value="form.owner" placeholder="请输入负责人" /></a-form-item>
        <a-form-item label="项目状态"><a-select v-model:value="form.status" :options="statusOptions" /></a-form-item>
        <a-form-item label="期刊 / 基金来源 / 项目级别"><a-input v-model:value="form.journal_or_funding_source" /></a-form-item>
        <a-form-item label="备注"><a-textarea v-model:value="form.remarks" :rows="5" /></a-form-item>
        <a-space>
          <a-button type="primary" :loading="saving" @click="saveProject">保存项目</a-button>
          <a-button @click="drawerOpen = false">取消</a-button>
        </a-space>
      </a-form>
    </a-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import {
  Alert as AAlert,
  Button as AButton,
  Card as ACard,
  Drawer as ADrawer,
  Empty as AEmpty,
  Form as AForm,
  FormItem as AFormItem,
  Input as AInput,
  Select as ASelect,
  Space as ASpace,
  Tag as ATag,
  Textarea as ATextarea,
  message,
} from 'ant-design-vue'
import { getDataQuality, getResearchProjects, getTopicSuggestions, postGenerateTopicSuggestions, postOmopExport, postResearchProject } from '../api/researchSupport'

const loading = ref(false)
const topicLoading = ref(false)
const omopLoading = ref(false)
const saving = ref(false)
const drawerOpen = ref(false)
const projects = ref<any[]>([])
const portfolio = ref<any>({})
const topics = ref<any[]>([])
const quality = ref<any>({})
const governance = ref<any[]>([])
const topicIsFallback = ref(false)
const form = reactive<any>({
  title: '',
  type: '课题',
  owner: '',
  status: '计划中',
  journal_or_funding_source: '',
  remarks: '',
})

const guideSteps = [
  { index: '01', title: '发现问题', desc: '从预警、Bundle、呼吸机、数据质量中识别可研究的临床差距。' },
  { index: '02', title: '一键立项', desc: '把 AI 推荐转为项目卡，补充负责人、状态、伦理和时间节点。' },
  { index: '03', title: '数据准备', desc: '先看缺失率和时间逻辑，再导出脱敏 OMOP CSV ZIP。' },
]
const typeOptions = ['论文', '课题', '基金', '伦理', '专利', '指南共识'].map((value) => ({ value, label: value }))
const statusOptions = ['计划中', '进行中', '投稿中', '已发表', '结题'].map((value) => ({ value, label: value }))
const missingRows = computed(() => Object.entries(quality.value?.missing_rate || {}).map(([field, rate]) => ({ field, rate: `${Math.round(Number(rate) * 100)}%` })))
const topicSourceLabel = computed(() => topicIsFallback.value ? '系统内置兜底建议' : 'AI / 数据摘要生成')
const statusRows = computed(() => Object.entries(portfolio.value?.by_status || {}).map(([key, value]) => ({ key, value })))
const milestones = computed(() => portfolio.value?.upcoming_milestones || [])

const titleMap: Record<string, string> = {
  'Prone Positioning Effectiveness in ARDS Patients': 'ARDS 患者俯卧位治疗效果研究',
  'Compliance with Sepsis 3-Hour Bundle and Patient Outcomes': '脓毒症 3 小时 Bundle 依从性与预后研究',
  'High Driving Pressure as a Predictor of Ventilator-Associated Lung Injury': '高驱动压暴露预测呼吸机相关肺损伤研究',
  'Impact of Data Quality Issues on Quality-Signal Reporting Accuracy': '数据质量问题对重症质控信号准确性的影响研究',
}
const questionMap: Record<string, string> = {
  'Does early prone positioning improve 28-day mortality among ICU patients diagnosed with ARDS?': '早期俯卧位治疗是否改善 ARDS ICU 患者 28 天结局？',
}
const fieldMap: Record<string, string> = {
  _id: '患者主键',
  hisPid: 'HIS 患者号',
  age: '年龄',
  birthday: '出生日期',
  sex: '性别',
  gender: '性别',
  clinicalDiagnosis: '临床诊断',
  icuAdmissionTime: 'ICU 入科时间',
  admissionTime: '入院时间',
}

function resetForm() {
  Object.assign(form, { title: '', type: '课题', owner: '', status: '计划中', journal_or_funding_source: '', remarks: '' })
}
function openProjectDrawer() {
  resetForm()
  drawerOpen.value = true
}
function createProjectFromTopic(topic: any) {
  Object.assign(form, {
    title: localizeTitle(topic.title),
    type: topic.study_design?.includes('QI') || topic.study_design?.includes('质量') ? '课题' : '论文',
    owner: '',
    status: '计划中',
    journal_or_funding_source: '',
    remarks: [
      `临床问题：${localizeQuestion(topic.clinical_question)}`,
      `数据依据：${localizeText(topic.data_basis)}`,
      `主要结局：${topic.primary_outcome || '待确认'}`,
      `伦理提示：${topic.ethical_risk || '需评估'}`,
    ].join('\n'),
  })
  drawerOpen.value = true
}
function localizeTitle(text: string) {
  return titleMap[text] || text || '未命名课题建议'
}
function localizeQuestion(text: string) {
  return questionMap[text] || text || '待明确临床问题'
}
function localizeText(text: string) {
  if (!text) return '暂无数据依据'
  return String(text)
    .replace('identified in the dataset', '条相关信号来自当前数据集')
    .replace('total ICU admissions', '例 ICU 入院记录')
    .replace('supports risk adjustment', '支持风险校正')
}
function fieldLabel(field: string) {
  return fieldMap[field] || field
}
function statusColor(status: string) {
  return status === '已发表' || status === '结题' ? 'green' : status === '投稿中' ? 'purple' : status === '进行中' ? 'blue' : 'gold'
}
function scoreColor(score: number) {
  return Number(score || 0) >= 85 ? 'green' : Number(score || 0) >= 70 ? 'cyan' : 'gold'
}
function confidenceLabel(value: string) {
  return ({ high: '置信度较高', medium: '置信度中等', low: '置信度较低' } as any)[value] || '需人工复核'
}

async function loadAll() {
  loading.value = true
  try {
    const [p, t, q] = await Promise.all([getResearchProjects(), getTopicSuggestions(), getDataQuality()])
    projects.value = p.data?.projects || []
    portfolio.value = p.data?.portfolio || {}
    topics.value = t.data?.topic_suggestions || []
    topicIsFallback.value = Boolean(t.data?.is_mock)
    quality.value = q.data?.report || {}
    governance.value = q.data?.recommendations || []
  } finally {
    loading.value = false
  }
}
async function generateTopics() {
  topicLoading.value = true
  try {
    const res = await postGenerateTopicSuggestions()
    topics.value = res.data?.topic_suggestions || []
    topicIsFallback.value = Boolean(res.data?.degraded)
    message.success(res.data?.degraded ? 'AI 暂不可用，已展示规则兜底建议' : '已生成课题建议')
  } finally {
    topicLoading.value = false
  }
}
async function exportOmop() {
  omopLoading.value = true
  try {
    const res = await postOmopExport({ patient_scope: 'all' })
    message.success(`OMOP 脱敏导出完成：${res.data?.task?.task_id || ''}`)
  } finally {
    omopLoading.value = false
  }
}
async function saveProject() {
  if (!form.title?.trim()) {
    message.warning('请先填写项目标题')
    return
  }
  saving.value = true
  try {
    await postResearchProject({ ...form })
    message.success('科研项目已保存')
    drawerOpen.value = false
    resetForm()
    await loadAll()
  } finally {
    saving.value = false
  }
}
onMounted(loadAll)
</script>

<style scoped>
.research-page {
  min-height: calc(100vh - 76px);
  padding: 20px;
  color: var(--text-main);
  background:
    radial-gradient(circle at 12% 0%, rgba(34, 211, 238, .12), transparent 30%),
    radial-gradient(circle at 88% 12%, rgba(20, 184, 166, .1), transparent 32%);
}
.research-hero {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 18px;
  padding: 18px;
  border: 1px solid rgba(80,199,255,.16);
  border-radius: 18px;
  background: linear-gradient(135deg, rgba(7, 25, 42, .95), rgba(5, 13, 25, .9));
}
.eyebrow {
  color: #67e8f9;
  font-weight: 900;
  letter-spacing: .12em;
  font-size: 12px;
}
h1, h2, h3, p { margin: 0; }
h1 { margin-top: 4px; color: #f0fbff; font-size: 28px; }
.research-hero p { margin-top: 8px; color: #9fc4d7; }
.guide-rail, .kpi-grid, .dashboard-grid, .topic-grid, .portfolio-grid {
  display: grid;
  gap: 12px;
}
.guide-rail {
  grid-template-columns: repeat(3, minmax(0, 1fr));
  margin: 14px 0;
}
.guide-card, .kpi-card, .project-card, .topic-card, .quality-summary article {
  border: 1px solid rgba(125,167,214,.14);
  border-radius: 16px;
  background: rgba(7, 20, 34, .72);
}
.guide-card { padding: 14px; display: grid; gap: 6px; }
.guide-card span { color: #22d3ee; font-weight: 900; }
.guide-card strong, .project-card h3, .topic-card h3 { color: #f0fbff; }
.guide-card p, .project-card p, .topic-card p, .topic-card dd, .omop-note p { color: #b7cfe0; }
.kpi-grid {
  grid-template-columns: repeat(4, minmax(0, 1fr));
  margin-bottom: 14px;
}
.kpi-card { padding: 14px; }
.kpi-card span, .kpi-card small { display: block; color: #8aa4b8; }
.kpi-card strong { display: block; margin: 5px 0; color: #f2fbff; font-size: 30px; line-height: 1; }
.kpi-card--cyan { background: linear-gradient(135deg, rgba(8, 64, 84, .74), rgba(7, 20, 34, .76)); }
.kpi-card--amber { background: linear-gradient(135deg, rgba(91, 55, 15, .68), rgba(7, 20, 34, .76)); }
.kpi-card--rose { background: linear-gradient(135deg, rgba(90, 20, 33, .68), rgba(7, 20, 34, .76)); }
.dashboard-grid {
  grid-template-columns: minmax(0, 1.15fr) minmax(380px, .85fr);
  margin-bottom: 14px;
}
.portfolio-grid {
  grid-template-columns: minmax(0, .8fr) minmax(0, 1.2fr);
  margin-bottom: 14px;
}
.panel { background: rgba(10,25,42,.92); border-radius: 16px; }
.empty-project {
  display: grid;
  place-items: center;
  gap: 12px;
  min-height: 310px;
  text-align: center;
  border: 1px dashed rgba(103,232,249,.24);
  border-radius: 16px;
  background: rgba(2,8,20,.22);
}
.empty-icon {
  width: 70px;
  height: 70px;
  display: grid;
  place-items: center;
  border-radius: 22px;
  color: #67e8f9;
  font-weight: 900;
  background: rgba(34,211,238,.1);
  border: 1px solid rgba(103,232,249,.2);
}
.empty-project p { max-width: 520px; color: #9fc4d7; }
.project-list { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 10px; }
.project-card { padding: 12px; display: grid; gap: 8px; }
.project-head, .topic-foot {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: center;
}
.topic-head {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  align-items: start;
}
.topic-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  min-width: 0;
}
.topic-tags :deep(.ant-tag) {
  max-width: 100%;
  white-space: normal;
  line-height: 1.35;
  word-break: break-word;
}
.topic-action {
  flex-shrink: 0;
}
.project-card small, .topic-foot, .panel-hint, .quality-row, .soft-empty { color: #88a2b4; }
.quality-summary { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-bottom: 12px; }
.quality-summary article { padding: 12px; }
.quality-summary span { display: block; color: #8aa4b8; }
.quality-summary strong { color: #e6f7ff; font-size: 24px; }
.quality-table {
  border: 1px solid rgba(125,167,214,.12);
  border-radius: 12px;
  overflow: hidden;
}
.quality-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 90px;
  padding: 9px 10px;
  border-bottom: 1px solid rgba(125,167,214,.1);
}
.quality-row--head { color: #67e8f9; font-weight: 800; background: rgba(8, 42, 62, .6); }
.omop-note {
  margin-top: 12px;
  padding: 12px;
  border-radius: 12px;
  background: rgba(8, 42, 62, .46);
}
.omop-note strong { color: #e6f7ff; }
.section-title {
  margin: 12px 0 8px;
  color: #e6f7ff;
  font-weight: 900;
}
.governance-list {
  display: grid;
  gap: 8px;
}
.governance-card {
  display: grid;
  grid-template-columns: 58px minmax(0, 1fr);
  gap: 8px;
  align-items: flex-start;
  padding: 10px;
  border-radius: 12px;
  background: rgba(2, 8, 20, .24);
}
.governance-card strong {
  display: block;
  color: #e6f7ff;
}
.governance-card p {
  margin-top: 3px;
  color: #9fc4d7;
}
.distribution-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 10px;
}
.distribution-grid article {
  padding: 12px;
  border: 1px solid rgba(125,167,214,.14);
  border-radius: 14px;
  background: rgba(2,8,20,.24);
}
.distribution-grid span {
  display: block;
  color: #8aa4b8;
}
.distribution-grid strong {
  color: #e6f7ff;
  font-size: 26px;
}
.milestone-list {
  display: grid;
  gap: 8px;
}
.milestone-list article {
  display: grid;
  gap: 3px;
  padding: 10px;
  border-radius: 12px;
  background: rgba(2,8,20,.24);
}
.milestone-list strong { color: #e6f7ff; }
.milestone-list span { color: #b7cfe0; }
.milestone-list small { color: #88a2b4; }
.topic-grid { grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); }
.topic-card {
  min-width: 0;
  padding: 14px;
  display: grid;
  gap: 12px;
  overflow: hidden;
}
.topic-card h3,
.topic-card p,
.topic-card dd,
.evidence-box span,
.topic-foot span {
  min-width: 0;
  overflow-wrap: anywhere;
  word-break: break-word;
}
.topic-card h3 {
  line-height: 1.45;
}
.topic-card > p,
.evidence-box span,
.topic-card dd {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.evidence-box {
  display: grid;
  gap: 4px;
  padding: 10px;
  border-radius: 12px;
  background: rgba(2, 8, 20, .24);
}
.evidence-box strong, .topic-card dt { color: #67e8f9; }
.topic-card dl { display: grid; gap: 8px; margin: 0; }
.topic-card dd { margin: 2px 0 0; }
.drawer-tip { margin-bottom: 12px; }
@media (max-width: 1280px) {
  .guide-rail, .kpi-grid, .dashboard-grid, .portfolio-grid { grid-template-columns: 1fr 1fr; }
}
@media (max-width: 760px) {
  .research-page { padding: 12px; }
  .research-hero { flex-direction: column; }
  .guide-rail, .kpi-grid, .dashboard-grid, .quality-summary, .portfolio-grid { grid-template-columns: 1fr; }
}
</style>
