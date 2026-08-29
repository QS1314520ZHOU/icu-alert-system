<template>
  <div class="nutr-page">
    <!-- 页面标题 -->
    <header class="nutr-header">
      <div class="nutr-header__left">
        <h1 class="page-title">营养支持工作台</h1>
        <span class="nutr-header__scope">{{ ctx.scopeLabel.value }}</span>
      </div>
      <div class="nutr-header__right">
        <a-input
          v-model:value="ctx.keyword.value"
          allow-clear
          placeholder="搜索床号 / 姓名 / 诊断"
          class="nutr-header__search"
        />
        <a-select
          v-model:value="ctx.riskFilter.value"
          :options="ctx.riskOptions"
          class="nutr-header__filter"
        />
        <a-button :loading="ctx.loading.value" @click="ctx.loadAll()">刷新</a-button>
      </div>
    </header>

    <!-- 加载状态 -->
    <div v-if="ctx.loading.value && !ctx.patients.value.length" class="loading-state">
      <a-spin tip="正在加载营养数据..." />
    </div>

    <!-- 可视化概览行 -->
    <div v-if="ctx.patients.value.length" class="nutr-viz-row">
      <div class="nutr-viz-card">
        <h4>营养路径分布</h4>
        <div ref="routeChartRef" class="nutr-viz-chart"></div>
      </div>
      <div class="nutr-viz-card">
        <h4>7日达标趋势</h4>
        <div ref="trendChartRef" class="nutr-viz-chart"></div>
      </div>
      <div class="nutr-viz-card nutr-viz-card--ring">
        <h4>数据完整性</h4>
        <DataCompletenessRing :value="dataCompleteness" :size="100" />
        <span class="nutr-viz-ring-label">{{ ctx.patients.value.length }} 人在科</span>
      </div>
    </div>

    <!-- 主体布局 -->
    <div v-else class="nutr-layout">
      <!-- 左侧：患者队列 -->
      <section class="nutr-queue">
        <div class="section-header">
          <h2 class="section-title">患者队列</h2>
          <span class="section-count">{{ ctx.urgentPatients.value.length }} 人</span>
        </div>

        <div v-if="!ctx.urgentPatients.value.length" class="empty-hint">
          <span>当前范围暂无需要营养复核的床位</span>
        </div>

        <div v-else class="nutr-queue__list">
          <NutritionPatientRow
            v-for="patient in ctx.urgentPatients.value"
            :key="patient.patient_id"
            :patient="patient"
            :tone="ctx.patientTone(patient)"
            :tolerance-label="getToleranceLabel(patient)"
            :tolerance-class="getToleranceClass(patient)"
            :refeeding-label="getRefeedingLabel(patient)"
            :refeeding-class="getRefeedingClass(patient)"
            :issue="ctx.shortNutritionIssue(patient)"
            :action-label="ctx.nextNutritionAction(patient)"
            @click="ctx.openPatient(patient)"
          />
        </div>
      </section>

      <!-- 右侧：任务面板 -->
      <aside class="nutr-sidebar">
        <!-- 今日待办 -->
        <div class="sidebar-card">
          <div class="sidebar-card__head">
            <h3 class="sidebar-card__title">今日待办</h3>
            <span class="sidebar-card__count">{{ ctx.todayTasks.value.length }} 项</span>
          </div>
          <div v-if="ctx.todayTasks.value.length" class="sidebar-card__list">
            <button
              v-for="task in ctx.todayTasks.value"
              :key="`task-${task.patient_id}-${task.action}`"
              type="button"
              :class="['sidebar-item', `tone-${task.tone}`]"
              @click="ctx.openById(task.patient_id)"
            >
              <div class="sidebar-item__content">
                <strong>{{ task.bed_no }}床</strong>
                <span>{{ task.action }}</span>
              </div>
              <small>{{ task.reason }}</small>
            </button>
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
              :key="`timeout-${item.patient_id}`"
              class="sidebar-item tone-danger"
            >
              <div class="sidebar-item__content">
                <strong>{{ item.bed_no }}床 {{ item.name || '' }}</strong>
                <span>{{ item.reason }}</span>
              </div>
              <a-button size="small" danger @click="ctx.openPatient(item)">处理</a-button>
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
            <button
              v-for="item in ctx.doctorConfirmItems.value"
              :key="`confirm-${item.patient_id || item.title}`"
              type="button"
              :class="['sidebar-item', `tone-${item.tone}`]"
              @click="item.patient_id ? ctx.openById(item.patient_id) : undefined"
            >
              <div class="sidebar-item__content">
                <strong>{{ item.bed_no ? `${item.bed_no}床` : '' }} {{ item.name || item.title || '' }}</strong>
                <span>{{ item.action || item.reason || '' }}</span>
              </div>
            </button>
          </div>
          <div v-else class="sidebar-empty">暂无待确认</div>
        </div>

        <!-- 路径分布 -->
        <div class="sidebar-card sidebar-card--compact">
          <div class="sidebar-card__head">
            <h3 class="sidebar-card__title">营养路径</h3>
          </div>
          <div class="route-grid">
            <button type="button" class="route-item" @click="ctx.riskFilter.value = 'EN'">
              <span class="route-dot route-dot--en" />
              <span>EN</span>
              <strong>{{ ctx.routeCount('EN') }}</strong>
            </button>
            <button type="button" class="route-item" @click="ctx.riskFilter.value = 'PN'">
              <span class="route-dot route-dot--pn" />
              <span>PN</span>
              <strong>{{ ctx.routeCount('PN') }}</strong>
            </button>
            <button type="button" class="route-item" @click="ctx.riskFilter.value = '混合'">
              <span class="route-dot route-dot--mix" />
              <span>混合</span>
              <strong>{{ ctx.routeCount('混合') }}</strong>
            </button>
            <button type="button" class="route-item" @click="ctx.riskFilter.value = '未开始'">
              <span class="route-dot route-dot--none" />
              <span>未开始</span>
              <strong>{{ ctx.routeCount('未开始') }}</strong>
            </button>
          </div>
        </div>

        <!-- 7日趋势 -->
        <div class="sidebar-card sidebar-card--compact">
          <div class="sidebar-card__head">
            <h3 class="sidebar-card__title">7日达标趋势</h3>
            <span class="sidebar-card__count">{{ ctx.avgTrend.value }}%</span>
          </div>
          <div class="trend-bars">
            <span
              v-for="(bar, idx) in ctx.wardTrend.value"
              :key="idx"
              :style="{ height: `${Math.max(8, bar)}%` }"
            />
          </div>
        </div>
      </aside>
    </div>

    <!-- 患者详情抽屉 -->
    <NutritionDrawer
      :open="ctx.drawerOpen.value"
      :patient="ctx.drawerPatient.value"
      :ai-advice="ctx.aiAdvice.value"
      :ai-loading="ctx.aiLoading.value"
      :tolerance-text="ctx.toleranceText.value"
      :glucose-range="ctx.glucoseRange.value"
      :glucose-points="ctx.glucosePoints.value"
      :quality-missing="ctx.qualityMissing.value"
      :delivery-source-label="ctx.deliverySourceLabel.value"
      :lab-rows="ctx.labRows.value"
      :level-text="ctx.levelText"
      :glucose-x="ctx.glucoseX"
      :glucose-y="ctx.glucoseY"
      :is-hot-tag="ctx.isHotTag"
      :fmt="ctx.fmt"
      @update:open="ctx.drawerOpen.value = $event"
      @load-ai="ctx.loadAiAdvice($event)"
      @create-task="ctx.createTask($event)"
      @close-task="ctx.closeTask($event)"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, onBeforeUnmount } from 'vue'
import { Button as AButton, Input as AInput, Select as ASelect, Spin as ASpin } from 'ant-design-vue'
import * as echarts from 'echarts/core'
import { PieChart, BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { useNutritionDashboard } from '../composables/useNutritionDashboard'
import NutritionPatientRow from '../components/nutrition/NutritionPatientRow.vue'
import NutritionDrawer from '../components/nutrition/NutritionDrawer.vue'
import DataCompletenessRing from '../components/charts/risk/DataCompletenessRing.vue'
import { icuGrid, icuTooltip, getChartColor } from '../charts/icuTheme'

echarts.use([PieChart, BarChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

const ctx = useNutritionDashboard()

// ── 营养路径饼图 ──────────────────────────────────────────────────
const routeChartRef = ref<HTMLElement>()
const trendChartRef = ref<HTMLElement>()
let routeChart: echarts.ECharts | null = null
let trendChart: echarts.ECharts | null = null

const dataCompleteness = computed(() => {
  const total = ctx.patients.value?.length || 0
  if (!total) return 0
  const withData = ctx.patients.value.filter((p: any) => p.calories_actual || p.route).length
  return Math.round((withData / total) * 100)
})

const routeChartOption = computed(() => ({
  tooltip: { trigger: 'item', formatter: '{b}: {c}人 ({d}%)' },
  legend: { bottom: 0, textStyle: { color: '#8C8C8C', fontSize: 11 } },
  series: [{
    type: 'pie',
    radius: ['40%', '65%'],
    center: ['50%', '45%'],
    label: { show: true, fontSize: 11, color: '#595959' },
    data: [
      { value: ctx.routeCount('EN'), name: '肠内(EN)', itemStyle: { color: getChartColor(0) } },
      { value: ctx.routeCount('PN'), name: '肠外(PN)', itemStyle: { color: getChartColor(1) } },
      { value: ctx.routeCount('混合'), name: '混合', itemStyle: { color: getChartColor(2) } },
      { value: ctx.routeCount('未开始'), name: '未开始', itemStyle: { color: '#D9D9D9' } },
    ].filter(d => d.value > 0),
  }],
}))

const trendChartOption = computed(() => {
  const data = ctx.wardTrend.value || []
  const days = data.map((_: any, i: number) => `${7 - i}天前`)
  return {
    ...icuGrid,
    ...icuTooltip,
    xAxis: { type: 'category', data: days.reverse(), axisLabel: { color: '#8C8C8C', fontSize: 11 }, axisLine: { lineStyle: { color: '#E8E8E8' } }, axisTick: { show: false } },
    yAxis: { type: 'value', max: 100, axisLabel: { color: '#8C8C8C', fontSize: 11, formatter: '{value}%' }, splitLine: { lineStyle: { color: '#F0F0F0', type: 'dashed' } } },
    series: [{
      type: 'bar',
      data: [...data].reverse(),
      itemStyle: { color: getChartColor(3), borderRadius: [4, 4, 0, 0] },
      barMaxWidth: 30,
      label: { show: true, position: 'top', fontSize: 10, color: '#8C8C8C', formatter: '{c}%' },
    }],
    grid: { left: 50, right: 16, top: 16, bottom: 40 },
  }
})

function initCharts() {
  if (routeChartRef.value) {
    routeChart = echarts.init(routeChartRef.value)
    routeChart.setOption(routeChartOption.value)
    const ro = new ResizeObserver(() => routeChart?.resize())
    ro.observe(routeChartRef.value)
  }
  if (trendChartRef.value) {
    trendChart = echarts.init(trendChartRef.value)
    trendChart.setOption(trendChartOption.value)
    const ro = new ResizeObserver(() => trendChart?.resize())
    ro.observe(trendChartRef.value)
  }
}

/* 行级状态映射 */
function getToleranceLabel(p: any): string {
  const level = p?.tolerance?.level
  if (level === 'danger') return '中断'
  if (level === 'warn') return '观察'
  if (level === 'stable') return '平稳'
  return '—'
}
function getToleranceClass(p: any): string {
  const level = p?.tolerance?.level
  if (level === 'danger') return 'tag-danger'
  if (level === 'warn') return 'tag-warn'
  if (level === 'stable') return 'tag-stable'
  return 'tag-muted'
}
function getRefeedingLabel(p: any): string {
  const level = p?.refeeding?.level
  if (level === 'danger') return '高危'
  if (level === 'warn') return '关注'
  if (level === 'stable') return '平稳'
  return '—'
}
function getRefeedingClass(p: any): string {
  const level = p?.refeeding?.level
  if (level === 'danger') return 'tag-danger'
  if (level === 'warn') return 'tag-warn'
  if (level === 'stable') return 'tag-stable'
  return 'tag-muted'
}

onMounted(() => {
  void ctx.loadAll()
  setTimeout(initCharts, 300)
})

onBeforeUnmount(() => {
  routeChart?.dispose()
  trendChart?.dispose()
  routeChart = null
  trendChart = null
})
</script>

<style scoped>
.nutr-page {
  min-height: calc(100vh - 76px);
  padding: var(--page-padding, 24px);
  background: var(--color-bg-page, #F6F7F9);
}

/* 可视化概览行 */
.nutr-viz-row {
  display: grid;
  grid-template-columns: 1fr 1fr 200px;
  gap: 16px;
  margin-bottom: var(--section-gap, 24px);
}

.nutr-viz-card {
  background: #fff;
  border: 1px solid #e8e8e8;
  border-radius: 8px;
  padding: 14px 16px;
}

.nutr-viz-card h4 {
  margin: 0 0 8px;
  font-size: 13px;
  font-weight: 600;
  color: #1a1a1a;
}

.nutr-viz-chart {
  width: 100%;
  height: 180px;
}

.nutr-viz-card--ring {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

.nutr-viz-ring-label {
  margin-top: 8px;
  font-size: 12px;
  color: #8c8c8c;
}

/* 头部 */
.nutr-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: var(--section-gap, 24px);
}
.nutr-header__left {
  flex: 1;
  min-width: 0;
}
.nutr-header__scope {
  display: inline-block;
  margin-top: 4px;
  padding: 2px 10px;
  border-radius: var(--radius-tag, 4px);
  font-size: var(--text-caption, 12px);
  color: var(--color-success, #16845B);
  background: var(--color-success-bg, rgba(22,132,91,0.08));
}
.nutr-header__right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}
.nutr-header__search { width: 220px; }
.nutr-header__filter { width: 140px; }

/* 加载状态 */
.loading-state {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 300px;
}

/* 主体布局 */
.nutr-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: var(--section-gap, 24px);
  align-items: start;
}

/* 左侧患者队列 */
.nutr-queue {
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
.nutr-queue__list {
  display: flex;
  flex-direction: column;
  gap: 6px;
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
.nutr-sidebar {
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
.sidebar-card--compact {
  padding: 12px;
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
.sidebar-card--compact .sidebar-card__head {
  padding-bottom: 8px;
  margin-bottom: 8px;
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
  cursor: pointer;
  font-family: inherit;
  color: inherit;
  text-align: left;
  width: 100%;
}
.sidebar-item:hover {
  background: var(--color-bg-surface-secondary, #F1F3F5);
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
.sidebar-item small {
  font-size: var(--text-caption, 12px);
  color: var(--color-text-secondary, #667085);
  flex-shrink: 0;
}

.sidebar-empty {
  padding: 16px;
  text-align: center;
  font-size: var(--text-caption, 12px);
  color: var(--color-text-secondary, #667085);
}

/* 路径分布 */
.route-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 6px;
}
.route-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px;
  border: 1px solid var(--color-border, #E3E7EC);
  border-radius: var(--radius-md, 6px);
  background: var(--color-bg-surface, #fff);
  cursor: pointer;
  font-family: inherit;
  color: inherit;
  text-align: left;
}
.route-item:hover {
  background: var(--color-bg-surface-secondary, #F1F3F5);
}
.route-item span {
  font-size: var(--text-caption, 12px);
  color: var(--color-text-secondary, #667085);
}
.route-item strong {
  margin-left: auto;
  font-family: var(--font-digit, 'Rajdhani', sans-serif);
  font-size: 16px;
  font-weight: 700;
  color: var(--color-text-primary, #18212B);
}
.route-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.route-dot--en { background: var(--color-success, #16845B); }
.route-dot--pn { background: var(--color-primary, #2563EB); }
.route-dot--mix { background: var(--color-warning, #B54708); }
.route-dot--none { background: var(--color-text-secondary, #667085); }

/* 7日趋势 */
.trend-bars {
  height: 80px;
  display: flex;
  align-items: flex-end;
  gap: 6px;
}
.trend-bars span {
  flex: 1;
  min-height: 6px;
  border-radius: 4px 4px 0 0;
  background: var(--color-success, #16845B);
  opacity: 0.7;
}

/* 响应式 */
@media (max-width: 1280px) {
  .nutr-layout {
    grid-template-columns: minmax(0, 1fr) 280px;
  }
}
@media (max-width: 1024px) {
  .nutr-layout {
    grid-template-columns: 1fr;
  }
  .nutr-sidebar {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
  }
}
@media (max-width: 768px) {
  .nutr-header {
    flex-direction: column;
  }
  .nutr-header__right {
    width: 100%;
    flex-wrap: wrap;
  }
  .nutr-header__search {
    flex: 1;
    min-width: 160px;
    width: auto;
  }
  .nutr-sidebar {
    grid-template-columns: 1fr;
  }
}
</style>
