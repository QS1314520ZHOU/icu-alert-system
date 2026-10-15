<template>
  <section class="nurse-home">
    <!-- 页面头部 -->
    <PageHeader
      title="护士首页"
      :subtitle="`责任护士 · ${home?.account?.dept || routeDept || '科室待识别'}`"
    >
      <template #actions>
        <span class="page-meta">{{ accountName }}</span>
        <span class="page-meta">{{ shiftText }}</span>
        <a-button size="small" @click="load">刷新</a-button>
      </template>
    </PageHeader>

    <!-- 加载/错误状态 -->
    <LoadingState v-if="loading" message="正在读取本班数据..." />
    <ErrorState v-else-if="error" :description="error" />

    <template v-else>
      <!-- KPI 摘要条 -->
      <MetricStrip
        :metrics="[
          { label: '我的床位', value: sortedBeds.length, unit: '人' },
          { label: '危急风险', value: criticalAlerts.length, unit: '项', variant: criticalAlerts.length > 0 ? 'danger' : 'success' },
          { label: '逾期任务', value: overdueCount, unit: '项', variant: overdueCount > 0 ? 'warning' : 'success' },
          { label: '工作负荷', value: `${workload.used_minutes || 0}/${workload.estimated_minutes || 0}`, unit: '分' },
        ]"
      />

      <!-- 主内容区 -->
      <div class="main-grid">
        <!-- 左列：床位 + 危急风险 -->
        <div class="col-left">
          <!-- 我的床位 - ICU床位地图 -->
          <ICUBedMap
            :beds="bedMapData"
            :columns="4"
            @bed-click="(bed) => bed.patientId && goPatient(bed.patientId)"
          />

          <!-- 危急/高风险 -->
          <section v-if="criticalAlerts.length" class="panel panel--critical">
            <div class="panel-head">
              <strong>⚠ 危急/高风险</strong>
              <span class="badge-danger">{{ criticalAlerts.length }}</span>
            </div>
            <div class="alert-list">
              <article
                v-for="item in criticalAlerts.slice(0, 8)"
                :key="item._id || item.created_at"
                class="alert-row"
              >
                <i :class="['alert-dot', priorityDot(item.priority)]"></i>
                <div class="alert-row__info">
                  <strong>{{ item.bed || '—' }}床 {{ item.patient_name || '—' }}</strong>
                  <span>{{ item.name || item.rule_id }}</span>
                </div>
                <small>{{ fmt(item.created_at) }}</small>
              </article>
            </div>
          </section>
        </div>

        <!-- 右列：任务 + 安全清单 + 交班 -->
        <div class="col-right">
          <!-- 本班任务 -->
          <NurseShiftTasks
            :tasks="timeline"
            :display-bed="displayBed"
            :fmt="fmt"
            @execute="handleTaskExecute"
          />

          <!-- 安全清单 -->
          <NurseSafetyChecklist
            :items="bundles"
            :display-name="displayName"
            :degraded="home?.bundle_degraded"
          />

          <!-- 交班入口 -->
          <NurseHandoffEntry
            :shift-end-soon="shiftEndSoon"
            :loading="handoffLoading"
            :bed-count="sortedBeds.length"
            :has-handover="!!handoffId"
            @generate="generateHandoff"
            @go-handover="goHandover"
          />
        </div>
      </div>

      <!-- 首次引导 -->
      <div v-if="showOnboarding" class="onboarding-mask" @click.self="dismissOnboarding">
        <div class="onboarding-card">
          <div class="onboarding-head">
            <strong>护士首页 3 步用法</strong>
            <a-button size="small" @click="dismissOnboarding">知道了</a-button>
          </div>
          <ol>
            <li>
              <b>看我的床位</b>
              <span>点击床位进入患者详情，红点表示有风险提醒。</span>
            </li>
            <li>
              <b>处理本班任务</b>
              <span>点击任务可执行、推迟、转交或标记不适用。</span>
            </li>
            <li>
              <b>下班前交班</b>
              <span>系统自动展开交班入口，一键生成交班单。</span>
            </li>
          </ol>
        </div>
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { Button as AButton } from 'ant-design-vue'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { postNurseHandoffGenerate } from '../api'
import { useAuthStore } from '../stores/auth'
import { useNurseHome } from '../composables/useNurseHome'
import { roleHomeConfig } from '../config/roleHomeConfig'
import { PageHeader, LoadingState, ErrorState, MetricStrip } from '../components/common/design-system'
import { ICUBedMap } from '../components/charts'
import type { BedInfo } from '../components/charts'
import NurseShiftTasks from '../components/nurse/NurseShiftTasks.vue'
import NurseSafetyChecklist from '../components/nurse/NurseSafetyChecklist.vue'
import NurseHandoffEntry from '../components/nurse/NurseHandoffEntry.vue'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const {
  loading,
  error,
  home,
  userId,
  accountName,
  routeDept,
  routeDeptCode,
  sortedBeds,
  workload,
  shiftText,
  shiftEndSoon,
  timeline,
  bundles,
  criticalAlerts,
  load,
  executeTask,
  goPatient,
  cleanDuplicateIdentityQuery,
  displayBed,
  fmt,
  displayName,
  priorityDot,
} = useNurseHome()

const showOnboarding = ref(false)
const handoffLoading = ref(false)
const handoffId = ref('')

// ── 计算 ──
const overdueCount = computed(() => timeline.value.filter((t: any) => t.status === 'overdue').length)

// ICU床位地图数据
const bedMapData = computed<BedInfo[]>(() => {
  return sortedBeds.value.map((bed: any) => {
    const riskLevel = String(bed.risk_level || '').toLowerCase()
    let status: BedInfo['status'] = 'normal'
    if (['critical', 'danger', 'red'].includes(riskLevel)) status = 'critical'
    else if (['high', 'warning', 'warn', 'medium'].includes(riskLevel)) status = 'high'
    return {
      bedNo: displayBed(bed.bed),
      patientId: bed.patient_id,
      patientName: bed.name || '未知',
      age: bed.age,
      gender: bed.gender,
      status,
      hr: bed.hr ?? bed.heart_rate,
      bp: bed.bp ?? (bed.sbp && bed.dbp ? `${bed.sbp}/${bed.dbp}` : undefined),
      spo2: bed.spo2 ?? bed.sp_o2,
      device: bed.device || bed.ventilator_mode,
      alertCount: bed.alert_count || (tasksByBed(bed.patient_id).length || 0),
    }
  })
})

// ── 按床位分组任务（避免在 v-for 中重复过滤） ──
const tasksByBedMap = computed(() => {
  const map = new Map<string, any[]>()
  for (const t of timeline.value) {
    const pid = (t as any).patient_id
    if (!pid) continue
    if (!map.has(pid)) map.set(pid, [])
    map.get(pid)!.push(t)
  }
  return map
})

function tasksByBed(patientId: string) {
  return tasksByBedMap.value.get(patientId) || []
}

// ── 任务操作 ──
async function handleTaskExecute(task: any, action: string) {
  await executeTask(task, action)
}

// ── 交班 ──
async function generateHandoff() {
  handoffLoading.value = true
  try {
    const payload: { user_id: string; patient_ids: string[]; shift_code: string; dept?: string; dept_code?: string } = {
      user_id: userId.value,
      patient_ids: sortedBeds.value.map((b: any) => b.patient_id),
      shift_code: home.value?.shift?.code || 'auto',
    }
    if (routeDeptCode.value) payload.dept_code = routeDeptCode.value
    else if (routeDept.value) payload.dept = routeDept.value
    const { data } = await postNurseHandoffGenerate(payload)
    handoffId.value = data?.data?.handoff_id || ''
    if (handoffId.value) {
      router.push({ path: '/handover', query: { ...route.query, handoff_id: handoffId.value } })
    }
  } catch {
    // 静默处理
  } finally {
    handoffLoading.value = false
  }
}

function goHandover() {
  router.push({ path: '/handover', query: route.query })
}

// ── 引导 ──
function dismissOnboarding() {
  showOnboarding.value = false
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(roleHomeConfig.nurse.onboardingKey, '1')
  }
}

// ── 生命周期 ──
onMounted(() => {
  auth.hydrateFromQuery(route.query)
  cleanDuplicateIdentityQuery()
  void load()
  if (typeof window !== 'undefined') {
    if (!window.localStorage.getItem(roleHomeConfig.nurse.onboardingKey)) {
      showOnboarding.value = true
    }
  }
})

watch(
  () => [
    route.query.user_id,
    route.query.userId,
    route.query.userName,
    route.query.useName,
    route.query.username,
    route.query.deptCode,
    route.query.dept_code,
    route.query.dept,
    route.query.department,
  ],
  () => {
    auth.hydrateFromQuery(route.query)
    void load()
  },
)
</script>

<style scoped>
.nurse-home {
  padding: var(--page-padding);
  padding-bottom: 80px;
  display: grid;
  gap: var(--section-gap);
  max-width: 1400px;
  margin: 0 auto;
}

/* ── 页面头部辅助信息 ── */
.page-meta {
  font-size: var(--text-caption);
  color: var(--color-text-secondary);
}

/* ── 主内容区 ── */
.main-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--section-gap);
  align-items: start;
}

.col-left,
.col-right {
  display: grid;
  gap: var(--element-gap-lg);
  align-content: start;
}

/* ── 面板通用 ── */
.panel {
  display: grid;
  gap: 10px;
  padding: var(--card-padding);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-bg-surface);
}

.panel--critical {
  border-color: var(--color-critical-border);
}

.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}

.panel-head strong {
  font-size: var(--text-card-title);
  font-weight: var(--text-card-title-weight);
  color: var(--color-text-primary);
}

.panel-head span {
  font-size: var(--text-caption);
  color: var(--color-text-secondary);
}

.badge-danger {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 20px;
  height: 20px;
  padding: 0 6px;
  border-radius: 999px;
  background: var(--color-danger-bg);
  color: var(--color-danger);
  font-size: var(--text-caption);
  font-weight: var(--weight-bold);
}

/* ── 告警列表 ── */
.alert-list {
  display: grid;
  gap: 1px;
}

.alert-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 0;
}

.alert-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.alert-dot.dot-p0 {
  background: var(--color-danger);
}

.alert-dot.dot-p1 {
  background: var(--color-warning);
}

.alert-dot.dot-p2 {
  background: var(--color-border-strong);
}

.alert-row__info {
  flex: 1;
  min-width: 0;
  display: grid;
  gap: 2px;
}

.alert-row__info strong {
  font-size: var(--text-body);
  font-weight: 500;
  color: var(--color-text-primary);
}

.alert-row__info span {
  font-size: var(--text-caption);
  color: var(--color-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.alert-row small {
  font-size: var(--text-caption);
  color: var(--color-text-secondary);
  flex-shrink: 0;
}

/* ── 引导弹窗 ── */
.onboarding-mask {
  position: fixed;
  inset: 0;
  z-index: 400;
  display: grid;
  place-items: center;
  background: rgba(17, 24, 39, 0.4);
  padding: 16px;
}

.onboarding-card {
  width: min(480px, 100%);
  display: grid;
  gap: 16px;
  padding: 24px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-bg-surface);
  box-shadow: var(--shadow-lg);
}

.onboarding-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.onboarding-head strong {
  font-size: var(--text-section-title);
  font-weight: var(--text-section-title-weight);
  color: var(--color-text-primary);
}

.onboarding-card ol {
  margin: 0;
  padding-left: 20px;
  display: grid;
  gap: 12px;
}

.onboarding-card li {
  color: var(--color-text-primary);
  line-height: 1.5;
}

.onboarding-card li b {
  display: block;
  font-size: var(--text-body);
  font-weight: var(--weight-semibold);
}

.onboarding-card li span {
  display: block;
  font-size: var(--text-caption);
  color: var(--color-text-secondary);
  margin-top: 2px;
}

/* ── 面板内空态保持紧凑 ── */
.panel :deep(.empty-state) {
  padding: 24px 16px;
}

/* ── 响应式 ── */
@media (max-width: 1024px) {
  .main-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
  .nurse-home {
    padding: 16px;
    padding-bottom: 60px;
  }
}
</style>
