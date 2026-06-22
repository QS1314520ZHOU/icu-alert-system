<template>
  <section class="followup-shell">
    <div class="followup-head">
      <div>
        <div class="followup-kicker">长期随访</div>
        <h3 class="followup-title">把 PICS 风险转成随访对象池与任务池</h3>
        <p class="followup-sub">住院内识别出的身体、认知、心理恢复风险，会在这里沉淀成随访案、任务和康复转介。</p>
      </div>
      <div class="followup-head-actions">
        <a-button size="small" :loading="loading" @click="loadOverview()">刷新</a-button>
        <a-button size="small" type="primary" ghost :loading="syncing" @click="refreshPicsAndEnroll">刷新 PICS 并入池</a-button>
      </div>
    </div>

    <a-spin :spinning="loading">
      <div class="followup-grid">
        <article :class="['followup-panel', 'followup-panel--case', `tone-${caseTone}`]">
          <div class="followup-panel-head">
            <div>
              <div class="followup-panel-title">随访对象池</div>
              <div class="followup-panel-sub">{{ followupCase ? '住院期风险已接入长期随访池' : '当前尚未形成长期随访案' }}</div>
            </div>
            <span :class="['followup-pill', `is-${caseTone}`]">{{ caseStatusText }}</span>
          </div>

          <div class="followup-metric-row">
            <div class="followup-metric">
              <span>综合评分</span>
              <strong>{{ currentAssessment?.overall_score ?? '—' }}</strong>
            </div>
            <div class="followup-metric">
              <span>开放任务</span>
              <strong>{{ summary.open_tasks ?? 0 }}</strong>
            </div>
            <div class="followup-metric">
              <span>待处理转介</span>
              <strong>{{ summary.pending_referrals ?? 0 }}</strong>
            </div>
          </div>

          <template v-if="followupCase">
            <div class="followup-chip-row">
              <span class="followup-chip">优先级 {{ priorityText }}</span>
              <span class="followup-chip">阶段 {{ stageText }}</span>
              <span class="followup-chip">来源 {{ followupCase?.source_module || 'pics_risk' }}</span>
              <span class="followup-chip">更新时间 {{ fmtTime(followupCase?.updated_at) }}</span>
            </div>
            <div class="followup-summary">
              <div class="followup-summary-label">风险摘要</div>
              <div class="followup-summary-text">{{ currentAssessment?.summary || '当前已纳入长期随访池，可继续生成任务或发起康复转介。' }}</div>
            </div>
            <div v-if="currentAssessment?.suggestion" class="followup-summary">
              <div class="followup-summary-label">建议动作</div>
              <div class="followup-summary-text">{{ currentAssessment?.suggestion }}</div>
            </div>
            <div class="followup-panel-actions">
              <a-button size="small" @click="updateCaseStatusAction(followupCase?.status === 'closed' ? 'active' : 'closed')">
                {{ followupCase?.status === 'closed' ? '重新激活随访案' : '关闭随访案' }}
              </a-button>
              <a-button
                v-if="props.openAiTab"
                size="small"
                type="link"
                @click="props.openAiTab?.()"
              >
                查看 AI / PICS 详情
              </a-button>
            </div>
          </template>

          <template v-else>
            <div class="followup-empty">
              <div class="followup-empty-title">{{ emptyTitle }}</div>
              <div class="followup-empty-text">{{ emptyText }}</div>
            </div>
          </template>
        </article>

        <article class="followup-panel followup-panel--actions">
          <div class="followup-panel-head">
            <div>
              <div class="followup-panel-title">一键转任务</div>
              <div class="followup-panel-sub">把 PICS 风险直接变成运营动作</div>
            </div>
          </div>

          <div class="followup-action-grid">
            <button class="followup-action" :disabled="actingTask || !currentAssessment" @click="createTask('pics_7d_call')">
              <strong>7天电话随访</strong>
              <span>围绕睡眠、焦虑、功能恢复和照护负担做首次回访。</span>
            </button>
            <button class="followup-action" :disabled="actingTask || !currentAssessment" @click="createTask('pics_30d_clinic')">
              <strong>30天门诊/视频复评</strong>
              <span>安排多维度复评，接住 ICU 转出后的恢复窗口。</span>
            </button>
            <button class="followup-action" :disabled="actingTask || !currentAssessment" @click="createTask('pics_screening')">
              <strong>补录 PICS 量表</strong>
              <span>把功能、认知和心理筛查补成后续跟踪基线。</span>
            </button>
            <button class="followup-action" :disabled="actingReferral || !currentAssessment" @click="createReferral('pics_rehab')">
              <strong>发起康复转介</strong>
              <span>直接转给康复医学科 / ICU 康复治疗师继续接力。</span>
            </button>
          </div>

          <div class="followup-inline-form">
            <input v-model.trim="manualTaskTitle" class="followup-input" type="text" maxlength="80" placeholder="补充一个自定义随访任务，例如：出院后 90 天认知复评" />
            <a-button size="small" type="primary" :loading="actingTask" @click="createManualTask">新增自定义任务</a-button>
          </div>
        </article>
      </div>

      <div class="followup-grid followup-grid--bottom">
        <article class="followup-panel">
          <div class="followup-panel-head">
            <div>
              <div class="followup-panel-title">随访任务</div>
              <div class="followup-panel-sub">当前患者的长期随访执行清单</div>
            </div>
            <span class="followup-count">{{ tasks.length }} 项</span>
          </div>

          <div v-if="tasks.length" class="followup-list">
            <article v-for="task in tasks" :key="task.task_id || task._id" class="followup-item">
              <div class="followup-item-top">
                <div>
                  <div class="followup-item-title">{{ task.title || '长期随访任务' }}</div>
                  <div class="followup-item-meta">到期 {{ fmtTime(task.due_at) }} · {{ task.category || 'followup' }}</div>
                </div>
                <span :class="['followup-pill', `is-${taskStatusTone(task.status)}`]">{{ taskStatusText(task.status) }}</span>
              </div>
              <div class="followup-item-desc">{{ task.description || '—' }}</div>
              <div class="followup-item-actions">
                <button v-if="task.status === 'open'" :disabled="actingTaskKey === task.task_id" @click="changeTaskStatus(task, 'in_progress')">开始执行</button>
                <button v-if="task.status !== 'completed'" :disabled="actingTaskKey === task.task_id" @click="changeTaskStatus(task, 'completed')">标记完成</button>
                <button v-if="task.status !== 'cancelled' && task.status !== 'completed'" :disabled="actingTaskKey === task.task_id" @click="changeTaskStatus(task, 'cancelled')">取消</button>
              </div>
            </article>
          </div>
          <div v-else class="followup-empty followup-empty--soft">暂无随访任务，先从上面的快捷动作生成一条。</div>
        </article>

        <article class="followup-panel">
          <div class="followup-panel-head">
            <div>
              <div class="followup-panel-title">康复转介</div>
              <div class="followup-panel-sub">把风险对象继续交给康复与门诊链路</div>
            </div>
            <span class="followup-count">{{ referrals.length }} 项</span>
          </div>

          <div v-if="referrals.length" class="followup-list">
            <article v-for="referral in referrals" :key="referral.referral_id || referral._id" class="followup-item">
              <div class="followup-item-top">
                <div>
                  <div class="followup-item-title">{{ referral.target_service || referral.referral_type || '康复转介' }}</div>
                  <div class="followup-item-meta">{{ referral.reason || '—' }}</div>
                </div>
                <span :class="['followup-pill', `is-${referralStatusTone(referral.status)}`]">{{ referralStatusText(referral.status) }}</span>
              </div>
              <div class="followup-item-desc">{{ referral.recommendation || '—' }}</div>
              <div class="followup-item-actions">
                <button v-if="referral.status === 'pending'" :disabled="actingReferralKey === referral.referral_id" @click="changeReferralStatus(referral, 'accepted')">已接收</button>
                <button v-if="referral.status !== 'completed'" :disabled="actingReferralKey === referral.referral_id" @click="changeReferralStatus(referral, 'scheduled')">已排期</button>
                <button v-if="referral.status !== 'completed'" :disabled="actingReferralKey === referral.referral_id" @click="changeReferralStatus(referral, 'completed')">完成</button>
              </div>
            </article>
          </div>
          <div v-else class="followup-empty followup-empty--soft">暂无康复转介，需要时可直接从上方发起。</div>
        </article>
      </div>

      <div v-if="error" class="followup-error">{{ error }}</div>
    </a-spin>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import dayjs from 'dayjs'
import { message } from 'ant-design-vue'
import {
  createPatientFollowupTask,
  createPatientRehabReferral,
  getPatientFollowupOverview,
  updateFollowupCaseStatus,
  updateFollowupTaskStatus,
  updateRehabReferralStatus,
  upsertPatientFollowupCase,
} from '../../api'
import { getOperatorIdentity } from '../../utils/operatorIdentity'

const props = defineProps<{
  patientId: string
  patient?: any
  picsRiskRecord?: any
  openAiTab?: () => void
}>()

const loading = ref(false)
const syncing = ref(false)
const actingTask = ref(false)
const actingReferral = ref(false)
const actingTaskKey = ref('')
const actingReferralKey = ref('')
const error = ref('')
const followupCase = ref<any>(null)
const tasks = ref<any[]>([])
const referrals = ref<any[]>([])
const summary = ref<any>({})
const manualTaskTitle = ref('')

const currentAssessment = computed(() => followupCase.value?.latest_assessment || props.picsRiskRecord?.assessment || null)
const caseTone = computed(() => {
  const severity = String(currentAssessment.value?.severity || '').toLowerCase()
  if (severity === 'high' || severity === 'critical') return 'rose'
  if (severity === 'warning') return 'amber'
  return followupCase.value ? 'cyan' : 'neutral'
})
const caseStatusText = computed(() => {
  const status = String(followupCase.value?.status || '')
  if (status === 'active') return '执行中'
  if (status === 'paused') return '已暂停'
  if (status === 'closed') return '已关闭'
  if (status === 'candidate') return '待转任务'
  return '未入池'
})
const priorityText = computed(() => ({
  high: '高',
  medium: '中',
  low: '低',
}[String(followupCase.value?.priority || '').toLowerCase()] || '中'))
const stageText = computed(() => ({
  task_ready: '待建任务',
  task_in_progress: '任务执行中',
  rehab_referred: '已发起转介',
  pool_enrolled: '已入对象池',
}[String(followupCase.value?.stage || '').toLowerCase()] || (followupCase.value?.stage || '待建任务')))
const emptyTitle = computed(() => currentAssessment.value ? '当前 PICS 风险尚未形成随访案' : '尚未发现可转长期随访的 PICS 风险')
const emptyText = computed(() => currentAssessment.value
  ? (currentAssessment.value?.summary || '可以先刷新 PICS 风险评估，再决定是否纳入随访池。')
  : '如果需要，可以先刷新 PICS 风险评估；达到预警阈值后会自动进入长期随访对象池。')

function fmtTime(value: any) {
  if (!value) return '—'
  const parsed = dayjs(value)
  return parsed.isValid() ? parsed.format('MM-DD HH:mm') : '—'
}

function taskStatusText(status: any) {
  const key = String(status || '').toLowerCase()
  return { open: '待执行', in_progress: '进行中', completed: '已完成', cancelled: '已取消' }[key] || '待执行'
}

function taskStatusTone(status: any) {
  const key = String(status || '').toLowerCase()
  if (key === 'completed') return 'cyan'
  if (key === 'cancelled') return 'neutral'
  if (key === 'in_progress') return 'amber'
  return 'rose'
}

function referralStatusText(status: any) {
  const key = String(status || '').toLowerCase()
  return { pending: '待处理', accepted: '已接收', scheduled: '已排期', completed: '已完成', rejected: '已拒绝', cancelled: '已取消' }[key] || '待处理'
}

function referralStatusTone(status: any) {
  const key = String(status || '').toLowerCase()
  if (key === 'completed') return 'cyan'
  if (key === 'scheduled' || key === 'accepted') return 'amber'
  if (key === 'rejected' || key === 'cancelled') return 'neutral'
  return 'rose'
}

function currentActor() {
  return getOperatorIdentity() || 'patient-detail'
}

function apiFailureMessage(data: any, fallback: string) {
  return data?.message || data?.detail || fallback
}

async function loadOverview(refreshPics = false) {
  if (!props.patientId) return
  loading.value = true
  error.value = ''
  try {
    const res = await getPatientFollowupOverview(props.patientId, { ensure_from_pics: true, refresh_pics: refreshPics })
    if (Number(res.data?.code ?? 0) !== 0) {
      throw new Error(apiFailureMessage(res.data, '长期随访数据加载失败'))
    }
    followupCase.value = res.data?.case || null
    tasks.value = Array.isArray(res.data?.tasks) ? res.data.tasks : []
    referrals.value = Array.isArray(res.data?.referrals) ? res.data.referrals : []
    summary.value = res.data?.summary || {}
  } catch (e: any) {
    error.value = e?.response?.data?.message || e?.message || '长期随访数据加载失败'
    followupCase.value = null
    tasks.value = []
    referrals.value = []
    summary.value = {}
  } finally {
    loading.value = false
  }
}

async function refreshPicsAndEnroll() {
  if (!props.patientId) return
  syncing.value = true
  try {
    const res = await upsertPatientFollowupCase(props.patientId, { source_module: 'pics_risk', refresh_pics: true, actor: currentActor() })
    if (Number(res.data?.code ?? 0) !== 0) {
      throw new Error(apiFailureMessage(res.data, '长期随访入池失败'))
    }
    message.success('已接入长期随访对象池')
    await loadOverview(false)
  } catch (e: any) {
    message.error(e?.response?.data?.message || e?.message || '长期随访入池失败')
  } finally {
    syncing.value = false
  }
}

async function createTask(templateKey: string) {
  if (!props.patientId) return
  actingTask.value = true
  try {
    const res = await createPatientFollowupTask(props.patientId, { template_key: templateKey, actor: currentActor() })
    if (Number(res.data?.code ?? 0) !== 0) {
      throw new Error(apiFailureMessage(res.data, '生成随访任务失败'))
    }
    message.success('随访任务已生成')
    await loadOverview(false)
  } catch (e: any) {
    message.error(e?.response?.data?.message || e?.message || '生成随访任务失败')
  } finally {
    actingTask.value = false
  }
}

async function createManualTask() {
  if (!manualTaskTitle.value) {
    message.warning('请先输入任务标题')
    return
  }
  actingTask.value = true
  try {
    const res = await createPatientFollowupTask(props.patientId, {
      title: manualTaskTitle.value,
      description: currentAssessment.value?.summary || 'PICS 长期随访补充任务',
      category: 'followup',
      actor: currentActor(),
    })
    if (Number(res.data?.code ?? 0) !== 0) {
      throw new Error(apiFailureMessage(res.data, '生成任务失败'))
    }
    manualTaskTitle.value = ''
    message.success('自定义随访任务已生成')
    await loadOverview(false)
  } catch (e: any) {
    message.error(e?.response?.data?.message || e?.message || '生成任务失败')
  } finally {
    actingTask.value = false
  }
}

async function changeTaskStatus(task: any, status: 'in_progress' | 'completed' | 'cancelled') {
  const taskId = String(task?.task_id || '')
  if (!taskId) return
  actingTaskKey.value = taskId
  try {
    const res = await updateFollowupTaskStatus(taskId, { status, actor: currentActor() })
    if (Number(res.data?.code ?? 0) !== 0) {
      throw new Error(apiFailureMessage(res.data, '任务状态更新失败'))
    }
    message.success('任务状态已更新')
    await loadOverview(false)
  } catch (e: any) {
    message.error(e?.response?.data?.message || e?.message || '任务状态更新失败')
  } finally {
    actingTaskKey.value = ''
  }
}

async function createReferral(templateKey: string) {
  if (!props.patientId) return
  actingReferral.value = true
  try {
    const res = await createPatientRehabReferral(props.patientId, { template_key: templateKey, actor: currentActor() })
    if (Number(res.data?.code ?? 0) !== 0) {
      throw new Error(apiFailureMessage(res.data, '康复转介创建失败'))
    }
    message.success('康复转介已创建')
    await loadOverview(false)
  } catch (e: any) {
    message.error(e?.response?.data?.message || e?.message || '康复转介创建失败')
  } finally {
    actingReferral.value = false
  }
}

async function changeReferralStatus(referral: any, status: 'accepted' | 'scheduled' | 'completed') {
  const referralId = String(referral?.referral_id || '')
  if (!referralId) return
  actingReferralKey.value = referralId
  try {
    const res = await updateRehabReferralStatus(referralId, { status, actor: currentActor() })
    if (Number(res.data?.code ?? 0) !== 0) {
      throw new Error(apiFailureMessage(res.data, '转介状态更新失败'))
    }
    message.success('转介状态已更新')
    await loadOverview(false)
  } catch (e: any) {
    message.error(e?.response?.data?.message || e?.message || '转介状态更新失败')
  } finally {
    actingReferralKey.value = ''
  }
}

async function updateCaseStatusAction(status: 'active' | 'closed') {
  const caseId = String(followupCase.value?.case_id || '')
  if (!caseId) return
  try {
    const res = await updateFollowupCaseStatus(caseId, { status, actor: currentActor() })
    if (Number(res.data?.code ?? 0) !== 0) {
      throw new Error(apiFailureMessage(res.data, '随访案状态更新失败'))
    }
    message.success(status === 'closed' ? '随访案已关闭' : '随访案已重新激活')
    await loadOverview(false)
  } catch (e: any) {
    message.error(e?.response?.data?.message || e?.message || '随访案状态更新失败')
  }
}

watch(() => props.patientId, () => {
  if (props.patientId) void loadOverview(false)
}, { immediate: true })
</script>

<style scoped>
.followup-shell { display: grid; gap: 14px; }
.followup-head { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; flex-wrap: wrap; }
.followup-kicker { color: var(--accent); font-size: 11px; letter-spacing: .18em; text-transform: uppercase; }
.followup-title { margin: 6px 0 0; color: var(--text-primary); font-size: 22px; font-weight: 800; }
.followup-sub { margin: 8px 0 0; color: #88a9c3; font-size: 13px; max-width: 760px; }
.followup-head-actions { display: inline-flex; gap: 8px; flex-wrap: wrap; }
.followup-grid { display: grid; grid-template-columns: 1.15fr .85fr; gap: 12px; }
.followup-grid--bottom { grid-template-columns: 1fr 1fr; }
.followup-panel { border: 1px solid rgba(80,199,255,.12); border-radius: var(--card-radius); background: var(--bg-surface) 0%, var(--bg-surface) 100%); padding: 16px; box-shadow: var(--card-shadow); }
.followup-panel--case.tone-rose { border-color: rgba(251,113,133,.22); }
.followup-panel--case.tone-amber { border-color: rgba(251,191,36,.22); }
.followup-panel-head { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; }
.followup-panel-title { color: var(--text-primary); font-size: 16px; font-weight: 800; }
.followup-panel-sub { margin-top: 4px; color: #88a9c3; font-size: 12px; }
.followup-pill { display: inline-flex; align-items: center; min-height: 28px; padding: 0 12px; border-radius: var(--card-radius); border: 1px solid rgba(80,199,255,.12); color: var(--text-primary); background: var(--bg-surface),.72); font-size: 12px; white-space: nowrap; }
.followup-pill.is-rose { color: var(--danger-soft); border-color: rgba(251,113,133,.25); background: var(--bg-surface),.72); }
.followup-pill.is-amber { color: var(--warning-soft); border-color: rgba(251,191,36,.24); background: var(--bg-surface),.74); }
.followup-pill.is-cyan { color: #bff5ff; }
.followup-pill.is-neutral { color: var(--text-secondary); border-color: rgba(148,163,184,.24); background: var(--bg-surface),.64); }
.followup-metric-row { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; margin-top: 14px; }
.followup-metric { border: 1px solid rgba(80,199,255,.1); border-radius: var(--card-radius); background: var(--bg-surface),.62); padding: 10px 12px; display: grid; gap: 4px; }
.followup-metric span { color: var(--accent); font-size: 11px; }
.followup-metric strong { color: var(--text-primary); font-size: 22px; line-height: 1.2; }
.followup-chip-row { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
.followup-chip { min-height: 28px; padding: 0 10px; border-radius: var(--card-radius); border: 1px solid rgba(80,199,255,.12); color: var(--text-primary); background: var(--bg-surface),.92); font-size: 11px; display: inline-flex; align-items: center; }
.followup-summary { margin-top: 12px; border: 1px solid rgba(80,199,255,.1); border-radius: var(--card-radius); background: var(--bg-surface),.76); padding: 12px; }
.followup-summary-label { color: var(--accent); font-size: 10px; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; }
.followup-summary-text { margin-top: 6px; color: #d8e8fb; font-size: 13px; line-height: 1.75; }
.followup-panel-actions { margin-top: 12px; display: flex; gap: 8px; flex-wrap: wrap; }
.followup-action-grid { display: grid; gap: 10px; margin-top: 12px; }
.followup-action { text-align: left; border: 1px solid rgba(80,199,255,.12); border-radius: var(--card-radius); background: var(--bg-surface),.72); padding: 12px 14px; color: inherit; cursor: pointer; transition: transform .18s ease, border-color .18s ease; }
.followup-action:hover:not(:disabled) { transform: translateY(-1px); border-color: rgba(103,232,249,.26); }
.followup-action:disabled { opacity: .58; cursor: not-allowed; }
.followup-action strong { display: block; color: var(--text-primary); font-size: 14px; }
.followup-action span { display: block; margin-top: 6px; color: #8fb0c6; font-size: 12px; line-height: 1.6; }
.followup-inline-form { display: grid; grid-template-columns: 1fr auto; gap: 10px; margin-top: 12px; }
.followup-input { width: 100%; border-radius: var(--card-radius); border: 1px solid rgba(80,199,255,.14); background: var(--bg-surface),.78); color: var(--text-primary); padding: 10px 12px; outline: none; }
.followup-input::placeholder { color: #6f8aa0; }
.followup-count { color: var(--accent); font-size: 12px; }
.followup-list { display: grid; gap: 10px; margin-top: 12px; }
.followup-item { border: 1px solid rgba(80,199,255,.1); border-radius: var(--card-radius); background: var(--bg-surface),.58); padding: 12px; }
.followup-item-top { display: flex; justify-content: space-between; gap: 10px; align-items: flex-start; }
.followup-item-title { color: var(--text-primary); font-size: 14px; font-weight: 700; }
.followup-item-meta { margin-top: 4px; color: #7f9bb2; font-size: 11px; }
.followup-item-desc { margin-top: 8px; color: var(--text-primary); font-size: 12px; line-height: 1.7; }
.followup-item-actions { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 10px; }
.followup-item-actions button { border: 1px solid rgba(80,199,255,.12); border-radius: var(--card-radius); background: var(--bg-surface),.92); color: var(--text-primary); padding: 5px 10px; cursor: pointer; }
.followup-empty { margin-top: 14px; border: 1px dashed rgba(80,199,255,.14); border-radius: var(--card-radius); padding: 16px; color: #89a2bb; background: var(--bg-surface),.42); }
.followup-empty--soft { margin-top: 12px; }
.followup-empty-title { color: var(--text-primary); font-size: 14px; font-weight: 700; }
.followup-empty-text { margin-top: 6px; line-height: 1.7; font-size: 12px; }
.followup-error { color: var(--danger-soft); font-size: 12px; }

html[data-theme='light'] .followup-title,
html[data-theme='light'] .followup-panel-title,
html[data-theme='light'] .followup-item-title,
html[data-theme='light'] .followup-metric strong,
html[data-theme='light'] .followup-empty-title { color: var(--text-secondary); }
html[data-theme='light'] .followup-sub,
html[data-theme='light'] .followup-panel-sub,
html[data-theme='light'] .followup-item-meta,
html[data-theme='light'] .followup-empty,
html[data-theme='light'] .followup-action span { color: var(--text-secondary); }
html[data-theme='light'] .followup-kicker { color: var(--brand); }
html[data-theme='light'] .followup-panel,
html[data-theme='light'] .followup-metric,
html[data-theme='light'] .followup-chip,
html[data-theme='light'] .followup-summary,
html[data-theme='light'] .followup-action,
html[data-theme='light'] .followup-item,
html[data-theme='light'] .followup-input,
html[data-theme='light'] .followup-pill {
  border-color: rgba(187,204,220,.72);
  background:
    var(--bg-surface), rgba(96,165,250,0) 40%),
    var(--bg-surface), rgba(243,248,252,.98));
  box-shadow: var(--card-shadow);
}
html[data-theme='light'] .followup-panel--case.tone-rose {
  border-color: rgba(251,113,133,.22);
  background:
    var(--bg-surface), rgba(251,113,133,0) 38%),
    var(--bg-surface), rgba(253,246,248,.98));
}
html[data-theme='light'] .followup-panel--case.tone-amber {
  border-color: rgba(245,158,11,.24);
  background:
    var(--bg-surface), rgba(245,158,11,0) 38%),
    var(--bg-surface), rgba(255,250,240,.98));
}
html[data-theme='light'] .followup-chip,
html[data-theme='light'] .followup-summary-text,
html[data-theme='light'] .followup-item-desc,
html[data-theme='light'] .followup-pill,
html[data-theme='light'] .followup-action strong { color: var(--text-secondary); }
html[data-theme='light'] .followup-metric span,
html[data-theme='light'] .followup-summary-label,
html[data-theme='light'] .followup-count { color: var(--text-secondary); }
html[data-theme='light'] .followup-input {
  color: var(--text-secondary);
  background: var(--bg-surface), rgba(247,250,253,.98));
  box-shadow: var(--card-shadow);
}
html[data-theme='light'] .followup-input::placeholder { color: #93a5b7; }
html[data-theme='light'] .followup-input:focus {
  border-color: rgba(59,130,246,.4);
  box-shadow: var(--card-shadow);
}
html[data-theme='light'] .followup-pill.is-rose {
  color: var(--danger-strong);
  border-color: rgba(251,113,133,.28);
  background: rgba(255,241,244,.98);
}
html[data-theme='light'] .followup-pill.is-amber {
  color: var(--warning);
  border-color: rgba(245,158,11,.26);
  background: rgba(255,247,237,.98);
}
html[data-theme='light'] .followup-pill.is-cyan {
  color: var(--brand);
  border-color: rgba(56,189,248,.24);
  background: rgba(240,249,255,.98);
}
html[data-theme='light'] .followup-pill.is-neutral {
  color: var(--text-secondary);
  border-color: rgba(148,163,184,.28);
  background: rgba(248,250,252,.98);
}
html[data-theme='light'] .followup-action:hover:not(:disabled) {
  border-color: rgba(59,130,246,.28);
  background:
    var(--bg-surface), rgba(96,165,250,0) 42%),
    var(--bg-surface), rgba(238,245,252,.98));
}
html[data-theme='light'] .followup-item-actions button {
  border-color: rgba(187,204,220,.72);
  background: var(--bg-surface);
  color: var(--text-secondary);
}
html[data-theme='light'] .followup-item-actions button:hover {
  border-color: rgba(59,130,246,.28);
  color: var(--brand);
}

@media (max-width: 1100px) {
  .followup-grid,
  .followup-grid--bottom { grid-template-columns: 1fr; }
}

@media (max-width: 720px) {
  .followup-head { gap: 12px; }
  .followup-title { font-size: 18px; }
  .followup-metric-row { grid-template-columns: 1fr; }
  .followup-inline-form { grid-template-columns: 1fr; }
  .followup-item-top { flex-direction: column; }
}
</style>
