<template>
  <div class="resp-page">
    <!-- 页面标题 -->
    <header class="resp-header">
      <div class="resp-header__left">
        <h1 class="page-title">呼吸治疗工作台</h1>
        <span class="resp-header__scope">{{ ctx.scopeLabel.value }}</span>
      </div>
      <div class="resp-header__right">
        <a-input
          v-model:value="ctx.keyword.value"
          allow-clear
          placeholder="搜索床号 / 姓名 / 诊断"
          class="resp-header__search"
        />
        <a-select
          v-model:value="ctx.riskFilter.value"
          :options="ctx.riskOptions"
          class="resp-header__filter"
        />
        <a-button :loading="ctx.loading.value" @click="ctx.loadAll()">刷新</a-button>
      </div>
    </header>

    <!-- 加载状态 -->
    <div v-if="ctx.loading.value && !ctx.patients.value.length" class="loading-state">
      <a-spin tip="正在加载呼吸治疗数据..." />
    </div>

    <!-- 可视化概览行 -->
    <div v-if="ctx.patients.value.length" class="resp-viz-row">
      <div class="resp-viz-card">
        <h4>通气参数分布</h4>
        <div ref="ventChartRef" class="resp-viz-chart"></div>
      </div>
      <div class="resp-viz-card">
        <h4>脱机路径进度</h4>
        <WorkflowDiagram
          :nodes="weaningNodes"
          direction="horizontal"
          size="small"
        />
      </div>
      <div class="resp-viz-card resp-viz-card--ring">
        <h4>数据完整性</h4>
        <DataCompletenessRing :value="ctx.completion.value?.data_quality?.percent ?? 0" :size="100" />
        <span class="resp-viz-ring-label">完成率 {{ ctx.completion.value?.percent ?? 0 }}%</span>
      </div>
    </div>

    <!-- 主体布局 -->
    <div v-else class="resp-layout">
      <!-- 左侧：患者队列 -->
      <section class="resp-queue">
        <div class="section-header">
          <h2 class="section-title">患者队列</h2>
          <span class="section-count">{{ ctx.urgentPatients.value.length }} 人</span>
        </div>

        <div v-if="!ctx.urgentPatients.value.length" class="empty-hint">
          <span>当前范围暂无机械通气患者</span>
        </div>

        <div v-else class="resp-queue__list">
          <RespiratoryPatientRow
            v-for="patient in ctx.urgentPatients.value"
            :key="patient.patient_id"
            :patient="patient"
            :tone="ctx.patientTone(patient)"
            :fio2="ctx.fmtVentParam('fio2', patient.fio2)"
            :peep="ctx.fmtVentParam('peep', patient.peep)"
            :pf="ctx.fmtVentParam('pf_ratio', patient.pf_ratio)"
            :sbt-label="patient.sbt_candidate_status?.status === 'candidate' ? 'SBT可评估' : '—'"
            :sbt-class="patient.sbt_candidate_status?.status === 'candidate' ? 'sbt-ok' : 'sbt-no'"
            :issue="ctx.shortIssue(patient)"
            :action-label="ctx.nextAction(patient)"
            @click="ctx.openPatient(patient)"
          />
        </div>

        <!-- SBT 评估队列 -->
        <div v-if="ctx.sbt.value?.todo?.length" class="resp-queue__sbt">
          <div class="section-header">
            <h2 class="section-title">SBT 可评估</h2>
            <span class="section-count">{{ ctx.sbt.value.todo.length }} 人</span>
          </div>
          <div class="sbt-rows">
            <div
              v-for="item in ctx.sbt.value.todo"
              :key="`sbt-${item.patient_id}`"
              class="sbt-row"
            >
              <span class="sbt-row__bed">{{ item.bed_no }}床</span>
              <span class="sbt-row__name">{{ item.name }}</span>
              <span class="sbt-row__score">候选 {{ ctx.sbtCandidateScore(item) }}/100</span>
              <span class="sbt-row__reason">{{ ctx.sbtCandidateReason(item) }}</span>
              <div class="sbt-row__actions">
                <a-button size="small" type="primary" @click.stop="ctx.recordSbt(item, 'completed')">完成</a-button>
                <a-button size="small" danger @click.stop="ctx.recordSbt(item, 'failed')">失败</a-button>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- 右侧：任务面板 -->
      <aside class="resp-sidebar">
        <!-- 今日待办 -->
        <div class="sidebar-card">
          <div class="sidebar-card__head">
            <h3 class="sidebar-card__title">今日待办</h3>
            <span class="sidebar-card__count">{{ ctx.todayTasks.value.length }} 项</span>
          </div>
          <div v-if="ctx.todayTasks.value.length" class="sidebar-card__list">
            <div
              v-for="task in ctx.todayTasks.value"
              :key="`task-${task.patient_id}-${task.title}`"
              :class="['sidebar-item', `tone-${task.tone}`]"
            >
              <div class="sidebar-item__content">
                <strong>{{ task.title }}</strong>
                <span>{{ task.reason }}</span>
              </div>
              <a-button size="small" @click="ctx.openTaskPatient(task)">查看</a-button>
            </div>
          </div>
          <div v-else class="sidebar-empty">暂无待办</div>
        </div>

        <!-- 即将超时 -->
        <div class="sidebar-card">
          <div class="sidebar-card__head">
            <h3 class="sidebar-card__title">即将超时</h3>
            <span class="sidebar-card__count">{{ ctx.timeoutItems.value.length }} 项</span>
          </div>
          <div v-if="ctx.timeoutItems.value.length" class="sidebar-card__list">
            <div
              v-for="item in ctx.timeoutItems.value"
              :key="`timeout-${item.patient_id}-${item.title}`"
              class="sidebar-item tone-danger"
            >
              <div class="sidebar-item__content">
                <strong>{{ item.bed_no }}床 {{ item.name || '' }}</strong>
                <span>{{ item.title }}</span>
              </div>
              <a-button size="small" danger @click="ctx.openTaskPatient(item)">处理</a-button>
            </div>
          </div>
          <div v-else class="sidebar-empty">暂无超时</div>
        </div>

        <!-- 需要医生确认 -->
        <div class="sidebar-card">
          <div class="sidebar-card__head">
            <h3 class="sidebar-card__title">需医生确认</h3>
            <span class="sidebar-card__count">{{ ctx.doctorConfirmItems.value.length }} 项</span>
          </div>
          <div v-if="ctx.doctorConfirmItems.value.length" class="sidebar-card__list">
            <div
              v-for="item in ctx.doctorConfirmItems.value"
              :key="`confirm-${item.patient_id}`"
              :class="['sidebar-item', `tone-${item.tone}`]"
            >
              <div class="sidebar-item__content">
                <strong>{{ item.bed_no }}床 {{ item.name || '' }}</strong>
                <span>{{ item.reason }}</span>
              </div>
              <a-button size="small" @click="ctx.openPatient(item)">查看</a-button>
            </div>
          </div>
          <div v-else class="sidebar-empty">暂无待确认</div>
        </div>

        <!-- 闭环进度 -->
        <div class="sidebar-card sidebar-card--progress">
          <div class="sidebar-card__head">
            <h3 class="sidebar-card__title">闭环进度</h3>
          </div>
          <div class="progress-row">
            <span>完成率</span>
            <strong>{{ ctx.completion.value?.percent ?? 100 }}%</strong>
            <div class="progress-bar">
              <div class="progress-bar__fill" :style="{ width: `${ctx.completion.value?.percent ?? 100}%` }" />
            </div>
          </div>
          <div class="progress-row">
            <span>数据质量</span>
            <strong>{{ ctx.completion.value?.data_quality?.percent ?? 100 }}%</strong>
            <div class="progress-bar">
              <div class="progress-bar__fill" :style="{ width: `${ctx.completion.value?.data_quality?.percent ?? 100}%` }" />
            </div>
          </div>
        </div>
      </aside>
    </div>

    <!-- 患者详情抽屉 -->
    <RespiratoryDrawer
      :open="ctx.drawerOpen.value"
      :patient="ctx.drawerPatient.value"
      :timeline="ctx.timeline.value"
      :forecast-view="ctx.forecastView.value"
      :airway-plan-view="ctx.airwayPlanView.value"
      :fmt-vent-param="ctx.fmtVentParam"
      :fmt="ctx.fmt"
      @update:open="ctx.drawerOpen.value = $event"
      @record-airway="ctx.recordAirway()"
      @save-difficult-airway="ctx.saveDifficultAirwayPlan()"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, watch, onBeforeUnmount } from 'vue'
import { Button as AButton, Input as AInput, Select as ASelect, Spin as ASpin } from 'ant-design-vue'
import * as echarts from 'echarts/core'
import { BarChart, GaugeChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { useRespiratoryDashboard } from '../composables/useRespiratoryDashboard'
import RespiratoryPatientRow from '../components/respiratory/RespiratoryPatientRow.vue'
import RespiratoryDrawer from '../components/respiratory/RespiratoryDrawer.vue'
import DataCompletenessRing from '../components/charts/risk/DataCompletenessRing.vue'
import WorkflowDiagram from '../components/charts/flow/WorkflowDiagram.vue'
import { icuGrid, icuTooltip, getChartColor } from '../charts/icuTheme'
import type { WorkflowNode } from '../components/charts'

echarts.use([BarChart, GaugeChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

const ctx = useRespiratoryDashboard()

// ── 通气参数分布图 ─────────────────────────────────────────────────
const ventChartRef = ref<HTMLElement>()
let ventChart: echarts.ECharts | null = null

const ventOption = computed(() => {
  const pts = ctx.patients.value || []
  const beds = pts.map((p: any) => p.bed_no || '?')
  const fio2 = pts.map((p: any) => Number(p.fio2 || 0))
  const peep = pts.map((p: any) => Number(p.peep || 0))
  const pf = pts.map((p: any) => Number(p.pf_ratio || 0))

  return {
    ...icuGrid,
    ...icuTooltip,
    legend: { data: ['FiO₂(%)', 'PEEP(cmH₂O)', 'P/F比'], bottom: 0, textStyle: { color: '#8C8C8C', fontSize: 11 } },
    xAxis: { type: 'category', data: beds, axisLabel: { color: '#8C8C8C', fontSize: 11 }, axisLine: { lineStyle: { color: '#E8E8E8' } }, axisTick: { show: false } },
    yAxis: { type: 'value', axisLabel: { color: '#8C8C8C', fontSize: 11 }, splitLine: { lineStyle: { color: '#F0F0F0', type: 'dashed' } } },
    series: [
      { name: 'FiO₂(%)', type: 'bar', data: fio2, itemStyle: { color: getChartColor(0), borderRadius: [4, 4, 0, 0] }, barMaxWidth: 20 },
      { name: 'PEEP(cmH₂O)', type: 'bar', data: peep, itemStyle: { color: getChartColor(1), borderRadius: [4, 4, 0, 0] }, barMaxWidth: 20 },
      { name: 'P/F比', type: 'bar', data: pf, itemStyle: { color: getChartColor(2), borderRadius: [4, 4, 0, 0] }, barMaxWidth: 20 },
    ],
    grid: { left: 50, right: 16, top: 12, bottom: 40 },
  }
})

function initVentChart() {
  if (!ventChartRef.value) return
  ventChart = echarts.init(ventChartRef.value)
  ventChart.setOption(ventOption.value)
  const ro = new ResizeObserver(() => ventChart?.resize())
  ro.observe(ventChartRef.value)
}

watch(ventOption, (opt) => { ventChart?.setOption(opt, true) }, { deep: true })

// ── 脱机路径节点 ──────────────────────────────────────────────────
const weaningNodes = computed<WorkflowNode[]>(() => {
  const totalPatients = ctx.patients.value?.length || 0
  const sbtCandidates = ctx.sbt.value?.todo?.length || 0
  const sbtDone = ctx.sbt.value?.done?.length || 0
  const completionPct = ctx.completion.value?.percent ?? 0

  return [
    { id: '1', name: '评估', status: totalPatients > 0 ? 'completed' : 'pending' as const, count: totalPatients },
    { id: '2', name: 'SBT筛选', status: sbtCandidates > 0 ? 'running' : 'completed' as const, count: sbtCandidates },
    { id: '3', name: 'SBT试验', status: sbtDone > 0 ? 'completed' : sbtCandidates > 0 ? 'pending' : 'unknown' as const, count: sbtDone },
    { id: '4', name: '脱机拔管', status: completionPct >= 80 ? 'completed' : completionPct >= 50 ? 'running' : 'pending' as const },
    { id: '5', name: '48h稳定', status: 'pending' as const },
  ]
})

onMounted(() => {
  void ctx.loadAll()
  setTimeout(initVentChart, 300)
})

onBeforeUnmount(() => {
  ventChart?.dispose()
  ventChart = null
})
</script>

<style scoped>
.resp-page {
  min-height: calc(100vh - 76px);
  padding: var(--page-padding, 24px);
  background: var(--color-bg-page, #F6F7F9);
}

/* 头部 */
.resp-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: var(--section-gap, 24px);
}
.resp-header__left {
  flex: 1;
  min-width: 0;
}
.resp-header__scope {
  display: inline-block;
  margin-top: 4px;
  padding: 2px 10px;
  border-radius: var(--radius-tag, 4px);
  font-size: var(--text-caption, 12px);
  color: var(--color-primary, #2563EB);
  background: var(--color-primary-bg, rgba(37,99,235,0.08));
}
.resp-header__right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}
.resp-header__search { width: 220px; }
.resp-header__filter { width: 140px; }

/* 可视化概览行 */
.resp-viz-row {
  display: grid;
  grid-template-columns: 1fr 1fr 200px;
  gap: 16px;
  margin-bottom: var(--section-gap, 24px);
}

.resp-viz-card {
  background: #fff;
  border: 1px solid #e8e8e8;
  border-radius: 8px;
  padding: 14px 16px;
}

.resp-viz-card h4 {
  margin: 0 0 8px;
  font-size: 13px;
  font-weight: 600;
  color: #1a1a1a;
}

.resp-viz-chart {
  width: 100%;
  height: 180px;
}

.resp-viz-card--ring {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

.resp-viz-ring-label {
  margin-top: 8px;
  font-size: 12px;
  color: #8c8c8c;
}

/* 加载状态 */
.loading-state {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 300px;
}

/* 主体布局 */
.resp-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: var(--section-gap, 24px);
  align-items: start;
}

/* 左侧患者队列 */
.resp-queue {
  display: flex;
  flex-direction: column;
  gap: var(--section-gap, 24px);
}
.section-header {
  display: flex;
  align-items: baseline;
  gap: 8px;
}
.section-count {
  font-size: var(--text-caption, 12px);
  color: var(--color-text-secondary, #667085);
}
.resp-queue__list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

/* SBT 队列 */
.resp-queue__sbt {
  margin-top: 8px;
}
.sbt-rows {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.sbt-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  border: 1px solid var(--color-border, #E3E7EC);
  border-radius: var(--radius-md, 6px);
  background: var(--color-bg-surface, #fff);
}
.sbt-row__bed {
  font-family: var(--font-digit, 'Rajdhani', sans-serif);
  font-size: 16px;
  font-weight: 700;
  color: var(--color-text-primary, #18212B);
  min-width: 36px;
}
.sbt-row__name {
  font-size: var(--text-body, 14px);
  color: var(--color-text-primary, #18212B);
  min-width: 60px;
}
.sbt-row__score {
  font-size: var(--text-caption, 12px);
  color: var(--color-text-secondary, #667085);
}
.sbt-row__reason {
  flex: 1;
  font-size: var(--text-caption, 12px);
  color: var(--color-text-secondary, #667085);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.sbt-row__actions {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
}

/* 空状态 */
.empty-hint {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 120px;
  border: 1px dashed var(--color-border, #E3E7EC);
  border-radius: var(--radius-lg, 8px);
  color: var(--color-text-secondary, #667085);
  font-size: var(--text-body, 14px);
}

/* 右侧边栏 */
.resp-sidebar {
  display: flex;
  flex-direction: column;
  gap: var(--element-gap-lg, 12px);
}

.sidebar-card {
  border: 1px solid var(--color-border, #E3E7EC);
  border-radius: var(--radius-lg, 8px);
  padding: var(--card-padding, 16px);
  background: var(--color-bg-surface, #fff);
}
.sidebar-card__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  padding-bottom: 10px;
  margin-bottom: 10px;
  border-bottom: 1px solid var(--color-border, #E3E7EC);
}
.sidebar-card__title {
  font-size: var(--text-card-title, 14px);
  font-weight: 650;
  color: var(--color-text-primary, #18212B);
  margin: 0;
}
.sidebar-card__count {
  font-size: var(--text-caption, 12px);
  color: var(--color-text-secondary, #667085);
}

.sidebar-card__list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.sidebar-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border: 1px solid var(--color-border, #E3E7EC);
  border-radius: var(--radius-md, 6px);
  background: var(--color-bg-surface, #fff);
  transition: border-color 0.15s;
}
.sidebar-item.tone-danger { border-left: 3px solid var(--color-danger, #D92D20); }
.sidebar-item.tone-warning { border-left: 3px solid var(--color-warning, #B54708); }
.sidebar-item.tone-info { border-left: 3px solid var(--color-primary, #2563EB); }

.sidebar-item__content {
  flex: 1;
  min-width: 0;
}
.sidebar-item__content strong {
  display: block;
  font-size: var(--text-body, 14px);
  font-weight: 600;
  color: var(--color-text-primary, #18212B);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.sidebar-item__content span {
  display: block;
  font-size: var(--text-caption, 12px);
  color: var(--color-text-secondary, #667085);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sidebar-empty {
  padding: 16px;
  text-align: center;
  font-size: var(--text-caption, 12px);
  color: var(--color-text-secondary, #667085);
}

/* 闭环进度 */
.sidebar-card--progress { padding: var(--card-padding, 16px); }
.progress-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.progress-row:last-child { margin-bottom: 0; }
.progress-row span {
  font-size: var(--text-caption, 12px);
  color: var(--color-text-secondary, #667085);
  min-width: 56px;
}
.progress-row strong {
  font-family: var(--font-digit, 'Rajdhani', sans-serif);
  font-size: 16px;
  font-weight: 700;
  color: var(--color-text-primary, #18212B);
  min-width: 40px;
  text-align: right;
}
.progress-bar {
  flex: 1;
  height: 6px;
  border-radius: 3px;
  background: var(--color-bg-surface-secondary, #F1F3F5);
  overflow: hidden;
}
.progress-bar__fill {
  height: 100%;
  border-radius: 3px;
  background: var(--color-success, #16845B);
  transition: width 0.3s ease;
}

/* 响应式 */
@media (max-width: 1280px) {
  .resp-layout {
    grid-template-columns: minmax(0, 1fr) 280px;
  }
}
@media (max-width: 1024px) {
  .resp-layout {
    grid-template-columns: 1fr;
  }
  .resp-sidebar {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
  }
}
@media (max-width: 768px) {
  .resp-header {
    flex-direction: column;
  }
  .resp-header__right {
    width: 100%;
    flex-wrap: wrap;
  }
  .resp-header__search {
    flex: 1;
    min-width: 160px;
    width: auto;
  }
  .resp-sidebar {
    grid-template-columns: 1fr;
  }
}
</style>
