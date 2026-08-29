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
        <button class="refresh-btn" @click="load">刷新</button>
      </template>
    </PageHeader>

    <!-- 加载/错误状态 -->
    <LoadingState v-if="loading" message="正在读取本班数据..." />
    <ErrorState v-else-if="error" :message="error" />

    <template v-else>
      <!-- KPI 摘要条 -->
      <div class="kpi-strip">
        <div class="kpi-item">
          <span class="kpi-label">我的床位</span>
          <strong class="kpi-value">{{ sortedBeds.length }}</strong>
        </div>
        <div class="kpi-item" :class="{ 'is-alert': criticalAlerts.length > 0 }">
          <span class="kpi-label">危急风险</span>
          <strong class="kpi-value">{{ criticalAlerts.length }}</strong>
        </div>
        <div class="kpi-item" :class="{ 'is-alert': overdueCount > 0 }">
          <span class="kpi-label">逾期任务</span>
          <strong class="kpi-value">{{ overdueCount }}</strong>
        </div>
        <div class="kpi-item">
          <span class="kpi-label">工作负荷</span>
          <strong class="kpi-value">{{ workload.used_minutes || 0 }}/{{ workload.estimated_minutes || 0 }}分</strong>
        </div>
      </div>

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
            <button @click="dismissOnboarding">知道了</button>
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
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { postNurseHandoffGenerate } from '../api'
import { useAuthStore } from '../stores/auth'
import { useNurseHome } from '../composables/useNurseHome'
import { roleHomeConfig } from '../config/roleHomeConfig'
import { PageHeader, LoadingState, ErrorState } from '../components/common/design-system'
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
  padding: var(--page-padding, 24px);
  padding-bottom: 80px;
  display: grid;
  gap: var(--section-gap, 24px);
  max-width: 1400px;
  margin: 0 auto;
}

/* ── 页面头部 ── */
.page-top {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
}

.page-top__left {
  display: grid;
  gap: 4px;
}

.page-top__title {
  font-size: var(--text-page-title, 24px);
  font-weight: var(--text-page-title-weight, 700);
  color: var(--color-text-primary, #18212B);
  margin: 0;
  line-height: 1.3;
}

.page-top__subtitle {
  font-size: var(--text-page-subtitle, 14px);
  color: var(--color-text-secondary, #667085);
}

.page-top__right {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
}

.page-top__meta {
  font-size: var(--text-caption, 12px);
  color: var(--color-text-secondary, #667085);
}

.refresh-btn {
  height: 32px;
  padding: 0 12px;
  border: 1px solid var(--color-border, #E3E7EC);
  border-radius: var(--radius-button, 6px);
  background: var(--color-bg-surface, #fff);
  color: var(--color-text-primary, #18212B);
  font-size: var(--text-caption, 12px);
  cursor: pointer;
  transition: all 0.15s;
}

.refresh-btn:hover {
  border-color: var(--color-primary, #2563EB);
  color: var(--color-primary, #2563EB);
}

/* ── 状态消息 ── */
.state-msg {
  padding: 40px;
  text-align: center;
  font-size: var(--text-body, 14px);
  color: var(--color-text-secondary, #667085);
  background: var(--color-bg-surface, #fff);
  border: 1px solid var(--color-border, #E3E7EC);
  border-radius: var(--radius-lg, 8px);
}

.state-msg.is-danger {
  color: var(--color-danger, #D92D20);
  background: var(--color-danger-bg);
  border-color: rgba(217, 45, 32, 0.2);
}

/* ── KPI 摘要条 ── */
.kpi-strip {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--element-gap, 8px);
}

.kpi-item {
  display: grid;
  gap: 4px;
  padding: var(--card-padding, 16px);
  border: 1px solid var(--color-border, #E3E7EC);
  border-radius: var(--radius-lg, 8px);
  background: var(--color-bg-surface, #fff);
}

.kpi-label {
  font-size: var(--text-caption, 12px);
  color: var(--color-text-secondary, #667085);
}

.kpi-value {
  font-size: var(--text-metric-normal, 20px);
  font-weight: var(--weight-bold, 700);
  color: var(--color-text-primary, #18212B);
  line-height: 1;
}

.kpi-item.is-alert {
  border-color: rgba(217, 45, 32, 0.3);
}

.kpi-item.is-alert .kpi-value {
  color: var(--color-danger, #D92D20);
}

/* ── 主内容区 ── */
.main-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--section-gap, 24px);
  align-items: start;
}

.col-left,
.col-right {
  display: grid;
  gap: var(--element-gap-lg, 12px);
  align-content: start;
}

/* ── 面板通用 ── */
.panel {
  display: grid;
  gap: 10px;
  padding: var(--card-padding, 16px);
  border: 1px solid var(--color-border, #E3E7EC);
  border-radius: var(--radius-lg, 8px);
  background: var(--color-bg-surface, #fff);
}

.panel--critical {
  border-color: rgba(217, 45, 32, 0.25);
}

.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}

.panel-head strong {
  font-size: var(--text-card-title, 14px);
  font-weight: var(--text-card-title-weight, 650);
  color: var(--color-text-primary, #18212B);
}

.panel-head span {
  font-size: var(--text-caption, 12px);
  color: var(--color-text-secondary, #667085);
}

.badge-danger {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 20px;
  height: 20px;
  padding: 0 6px;
  border-radius: 10px;
  background: var(--color-danger-bg);
  color: var(--color-danger, #D92D20);
  font-size: 11px;
  font-weight: 700;
}

/* ── 床位网格 ── */
.bed-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 8px;
}

.bed-card {
  position: relative;
  display: grid;
  gap: 4px;
  padding: 10px 12px 10px 28px;
  border: 1px solid var(--color-border, #E3E7EC);
  border-radius: var(--radius-md, 6px);
  cursor: pointer;
  transition: all 0.15s;
}

.bed-card:hover {
  border-color: var(--color-primary, #2563EB);
  background: var(--color-bg-surface-secondary, #F1F3F5);
}

.bed-dot {
  position: absolute;
  left: 10px;
  top: 14px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.bed-dot.is-critical { background: var(--color-danger, #D92D20); }
.bed-dot.is-warn { background: var(--color-warning, #B54708); }
.bed-dot.is-muted { background: var(--color-border, #E3E7EC); }

.bed-card__top {
  display: flex;
  align-items: center;
  gap: 0;
}

.bed-card__top strong {
  font-size: var(--text-body, 14px);
  font-weight: 600;
  color: var(--color-text-primary, #18212B);
}

.bed-card__name {
  font-size: var(--text-caption, 12px);
  color: var(--color-text-secondary, #667085);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bed-card__badge {
  position: absolute;
  top: 6px;
  right: 6px;
  padding: 1px 6px;
  border-radius: 8px;
  background: var(--color-warning-bg);
  color: var(--color-warning, #B54708);
  font-size: 10px;
  font-weight: 600;
}

.empty-hint {
  padding: 20px;
  text-align: center;
  font-size: var(--text-caption, 12px);
  color: var(--color-text-secondary, #667085);
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
  background: var(--color-danger, #D92D20);
  box-shadow: 0 0 4px rgba(217, 45, 32, 0.4);
}

.alert-dot.dot-p1 {
  background: var(--color-warning, #B54708);
}

.alert-dot.dot-p2 {
  background: var(--color-border, #E3E7EC);
}

.alert-row__info {
  flex: 1;
  min-width: 0;
  display: grid;
  gap: 2px;
}

.alert-row__info strong {
  font-size: var(--text-body, 14px);
  font-weight: 500;
  color: var(--color-text-primary, #18212B);
}

.alert-row__info span {
  font-size: var(--text-caption, 12px);
  color: var(--color-text-secondary, #667085);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.alert-row small {
  font-size: var(--text-caption, 12px);
  color: var(--color-text-secondary, #667085);
  flex-shrink: 0;
}

/* ── 引导弹窗 ── */
.onboarding-mask {
  position: fixed;
  inset: 0;
  z-index: 400;
  display: grid;
  place-items: center;
  background: rgba(0, 0, 0, 0.3);
  padding: 16px;
}

.onboarding-card {
  width: min(480px, 100%);
  display: grid;
  gap: 16px;
  padding: 24px;
  border-radius: var(--radius-xl, 10px);
  background: var(--color-bg-surface, #fff);
  box-shadow: var(--shadow-xl);
}

.onboarding-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.onboarding-head strong {
  font-size: var(--text-section-title, 16px);
  font-weight: var(--text-section-title-weight, 650);
  color: var(--color-text-primary, #18212B);
}

.onboarding-head button {
  height: 32px;
  padding: 0 12px;
  border: 1px solid var(--color-border, #E3E7EC);
  border-radius: var(--radius-button, 6px);
  background: transparent;
  color: var(--color-text-secondary, #667085);
  font-size: var(--text-caption, 12px);
  cursor: pointer;
}

.onboarding-card ol {
  margin: 0;
  padding-left: 20px;
  display: grid;
  gap: 12px;
}

.onboarding-card li {
  color: var(--color-text-primary, #18212B);
  line-height: 1.5;
}

.onboarding-card li b {
  display: block;
  font-size: var(--text-body, 14px);
  font-weight: 600;
}

.onboarding-card li span {
  display: block;
  font-size: var(--text-caption, 12px);
  color: var(--color-text-secondary, #667085);
  margin-top: 2px;
}

/* ── 响应式 ── */
@media (max-width: 1024px) {
  .main-grid {
    grid-template-columns: 1fr;
  }

  .kpi-strip {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 640px) {
  .nurse-home {
    padding: 16px;
    padding-bottom: 60px;
  }

  .page-top {
    flex-direction: column;
    gap: 8px;
  }

  .page-top__right {
    width: 100%;
    justify-content: flex-start;
  }

  .kpi-strip {
    grid-template-columns: repeat(2, 1fr);
  }

  .bed-grid {
    grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  }
}
</style>
