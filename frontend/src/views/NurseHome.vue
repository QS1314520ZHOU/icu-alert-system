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
        <span v-if="workload.estimated_minutes" class="page-meta">工作负荷 {{ workload.used_minutes || 0 }}/{{ workload.estimated_minutes }} 分钟</span>
        <a-button size="small" @click="load">刷新</a-button>
      </template>
    </PageHeader>

    <!-- 加载/错误状态 -->
    <LoadingState v-if="loading" message="正在读取本班数据..." />
    <ErrorState v-else-if="error" :description="error" />

    <template v-else>
      <!-- 床位临床概览（我的床位；未匹配到分管时展示全科） -->
      <WardClinicalBoard
        class="nurse-board"
        :title="myBedIds.length ? `我的床位 · 逾期任务 ${overdueCount} 项` : '科室床位概览（未匹配到分管床位）'"
        :patient-ids="myBedIds"
        :scope-label="myBedIds.length ? '我的床位' : '在科患者'"
      />

      <!-- 主内容区 -->
      <div class="main-grid">
        <!-- 左列：床位 + 危急风险 -->
        <div class="col-left">
          <!-- 危急/高风险 -->
          <section v-if="criticalAlerts.length" class="panel panel--critical">
            <div class="panel-head">
              <strong>危急/高风险</strong>
              <span class="badge-danger">{{ criticalAlerts.length }}</span>
            </div>
            <div class="alert-list">
              <article
                v-for="item in criticalAlerts.slice(0, 8)"
                :key="item._id || item.created_at"
                class="alert-row"
                @click="item.patient_id && goPatient(item.patient_id)"
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
import { PageHeader, LoadingState, ErrorState } from '../components/common/design-system'
import WardClinicalBoard from '../components/home/WardClinicalBoard.vue'
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

const myBedIds = computed<string[]>(() => sortedBeds.value.map((b: any) => String(b.patient_id || '')).filter(Boolean))
const handoffLoading = ref(false)
const handoffId = ref('')

// ── 计算 ──
const overdueCount = computed(() => timeline.value.filter((t: any) => t.status === 'overdue').length)

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

// ── 生命周期 ──
onMounted(() => {
  auth.hydrateFromQuery(route.query)
  cleanDuplicateIdentityQuery()
  void load()
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
.nurse-board { margin-bottom: 12px; }
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

.alert-row { cursor: pointer;
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
