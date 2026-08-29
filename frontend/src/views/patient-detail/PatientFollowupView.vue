<template>
  <div class="followup-layout">
    <a-tabs v-model:activeKey="activeTab" type="card">
      <!-- PICS 长期随访 -->
      <a-tab-pane key="pics" tab="PICS 长期随访">
        <Suspense>
          <LongTermFollowupTab :patient-id="patientId" :patient="patient" />
          <template #fallback><div class="loading-placeholder"><a-spin tip="加载随访数据..." /></div></template>
        </Suspense>
      </a-tab-pane>

      <!-- 随访任务 -->
      <a-tab-pane key="tasks" tab="随访任务">
        <section class="followup-section">
          <div class="section-header">
            <h3>随访任务</h3>
            <a-button size="small" @click="loadTasks" :loading="tasksLoading">刷新</a-button>
          </div>
          <a-spin :spinning="tasksLoading">
            <div v-if="tasks.length" class="task-list">
              <div v-for="task in tasks" :key="task._id" class="task-card">
                <div class="task-header">
                  <span class="task-type">{{ taskTypeLabel(task.template_key) }}</span>
                  <a-tag :color="taskStatusColor(task.status)">{{ taskStatusLabel(task.status) }}</a-tag>
                  <span class="task-time">{{ fmtTime(task.due_date || task.created_at) }}</span>
                </div>
                <p class="task-desc">{{ task.description || task.notes || '' }}</p>
                <div class="task-actions">
                  <a-button
                    size="small"
                    type="primary"
                    :loading="actingTaskId === task._id"
                    @click="completeTask(task)"
                    v-if="task.status === 'open' || task.status === 'in_progress'"
                  >完成</a-button>
                  <a-button
                    size="small"
                    @click="cancelTask(task)"
                    v-if="task.status === 'open'"
                  >跳过</a-button>
                </div>
              </div>
            </div>
            <a-empty v-else description="暂无随访任务" :image-style="{ height: '40px' }" />
          </a-spin>
        </section>
      </a-tab-pane>

      <!-- 康复转介 -->
      <a-tab-pane key="rehab" tab="康复转介">
        <section class="followup-section">
          <div class="section-header">
            <h3>康复转介</h3>
            <a-button size="small" @click="loadReferrals" :loading="referralsLoading">刷新</a-button>
          </div>
          <a-spin :spinning="referralsLoading">
            <div v-if="referrals.length" class="referral-list">
              <div v-for="ref in referrals" :key="ref._id" class="referral-card">
                <div class="referral-header">
                  <span class="referral-type">{{ ref.template_key || '康复转介' }}</span>
                  <a-tag :color="referralStatusColor(ref.status)">{{ referralStatusLabel(ref.status) }}</a-tag>
                  <span class="referral-time">{{ fmtTime(ref.created_at) }}</span>
                </div>
                <p class="referral-reason">{{ ref.reason || ref.notes || '' }}</p>
                <div class="referral-actions">
                  <a-button
                    size="small"
                    type="primary"
                    :loading="actingReferralId === ref._id"
                    @click="completeReferral(ref)"
                    v-if="ref.status === 'pending' || ref.status === 'accepted'"
                  >完成</a-button>
                </div>
              </div>
            </div>
            <a-empty v-else description="暂无康复转介" :image-style="{ height: '40px' }" />
          </a-spin>
        </section>
      </a-tab-pane>
    </a-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, defineAsyncComponent } from 'vue'
import { useRoute } from 'vue-router'
import { usePatientDetail } from '../../composables/usePatientDetail'
import {
  getPatientFollowupTasks,
  updateFollowupTaskStatus,
  getPatientRehabReferrals,
  updateRehabReferralStatus,
} from '../../api/index'

const LongTermFollowupTab = defineAsyncComponent(() => import('../../components/patient-detail/LongTermFollowupTab.vue'))

const route = useRoute()
const { patient } = usePatientDetail()

const patientId = computed(() => String(route.params.id || ''))
const activeTab = ref('pics')

// ── Tasks ───────────────────────────────────────────────
const tasks = ref<any[]>([])
const tasksLoading = ref(false)
const actingTaskId = ref('')

async function loadTasks() {
  if (!patientId.value) return
  tasksLoading.value = true
  try {
    const res = await getPatientFollowupTasks(patientId.value)
    tasks.value = res?.data?.data || res?.data || []
  } catch (e) {
    console.warn('[FollowupView] load tasks failed:', e)
  } finally {
    tasksLoading.value = false
  }
}

async function completeTask(task: any) {
  actingTaskId.value = task._id
  try {
    await updateFollowupTaskStatus(task._id, { status: 'completed' })
    await loadTasks()
  } finally {
    actingTaskId.value = ''
  }
}

async function cancelTask(task: any) {
  actingTaskId.value = task._id
  try {
    await updateFollowupTaskStatus(task._id, { status: 'cancelled' })
    await loadTasks()
  } finally {
    actingTaskId.value = ''
  }
}

// ── Referrals ───────────────────────────────────────────
const referrals = ref<any[]>([])
const referralsLoading = ref(false)
const actingReferralId = ref('')

async function loadReferrals() {
  if (!patientId.value) return
  referralsLoading.value = true
  try {
    const res = await getPatientRehabReferrals(patientId.value)
    referrals.value = res?.data?.data || res?.data || []
  } catch (e) {
    console.warn('[FollowupView] load referrals failed:', e)
  } finally {
    referralsLoading.value = false
  }
}

async function completeReferral(ref_: any) {
  actingReferralId.value = ref_._id
  try {
    await updateRehabReferralStatus(ref_._id, { status: 'completed' })
    await loadReferrals()
  } finally {
    actingReferralId.value = ''
  }
}

// ── Helpers ─────────────────────────────────────────────
function fmtTime(t: string) {
  if (!t) return ''
  try { return new Date(t).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) } catch { return t }
}

function taskTypeLabel(key: string) {
  const map: Record<string, string> = {
    'pics_physical': '体能恢复',
    'pics_cognitive': '认知评估',
    'pics_mental': '心理筛查',
    'nutrition_followup': '营养随访',
    'respiratory_followup': '呼吸随访',
  }
  return map[key] || key || '随访任务'
}

function taskStatusColor(status: string) {
  if (status === 'completed') return 'success'
  if (status === 'in_progress') return 'processing'
  if (status === 'cancelled') return 'default'
  return 'warning'
}

function taskStatusLabel(status: string) {
  const map: Record<string, string> = { open: '待执行', in_progress: '进行中', completed: '已完成', cancelled: '已取消' }
  return map[status] || status
}

function referralStatusColor(status: string) {
  if (status === 'completed') return 'success'
  if (status === 'accepted') return 'processing'
  return 'warning'
}

function referralStatusLabel(status: string) {
  const map: Record<string, string> = { pending: '待处理', accepted: '已接收', completed: '已完成', rejected: '已拒绝' }
  return map[status] || status
}

onMounted(() => {
  loadTasks()
  loadReferrals()
})
</script>

<style scoped>
.followup-layout {
  padding: 0;
}

.loading-placeholder {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 200px;
}

.followup-section {
  background: #fff;
  border: 1px solid #e8e8e8;
  border-radius: 8px;
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
  font-size: 15px;
  font-weight: 600;
  color: #1a1a1a;
}

.task-list, .referral-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.task-card, .referral-card {
  border: 1px solid #f0f0f0;
  border-radius: 6px;
  padding: 12px;
  background: #fafbfc;
}

.task-header, .referral-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.task-type, .referral-type {
  font-size: 13px;
  font-weight: 600;
  color: #333;
}

.task-time, .referral-time {
  margin-left: auto;
  font-size: 11px;
  color: #999;
}

.task-desc, .referral-reason {
  margin: 0 0 8px;
  font-size: 13px;
  color: #666;
  line-height: 1.5;
}

.task-actions, .referral-actions {
  display: flex;
  gap: 8px;
}
</style>
