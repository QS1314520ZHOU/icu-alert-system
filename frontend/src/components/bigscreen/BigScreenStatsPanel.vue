<template>
  <aside class="panel panel-right">
    <section class="stat-block stat-block--cyan">
      <div class="stat-head">
        <div class="stat-title-group">
          <div class="panel-kicker">结构总览</div>
          <div class="panel-title">科室统计</div>
        </div>
        <div class="panel-scale">在院分布</div>
      </div>
      <div class="chart-wrap">
        <BigScreenChart :option="deptOption" :init-options="chartInitOptions" autoresize />
      </div>
    </section>
    <section class="stat-block stat-block--green">
      <div class="stat-head">
        <div class="stat-title-group">
          <div class="panel-kicker">流程指标</div>
          <div class="panel-title">集束化合规率</div>
        </div>
        <div class="panel-scale">护理闭环</div>
      </div>
      <div class="chart-wrap">
        <BigScreenChart :option="bundleOption" :init-options="chartInitOptions" autoresize />
      </div>
    </section>
    <section class="stat-block stat-block--amber">
      <div class="stat-head">
        <div class="stat-title-group">
          <div class="panel-kicker">风险走势</div>
          <div class="panel-title">近24小时预警趋势</div>
        </div>
        <div class="panel-scale">24 小时滚动</div>
      </div>
      <div class="chart-wrap">
        <BigScreenChart :option="alertTrendOption" :init-options="chartInitOptions" autoresize />
      </div>
    </section>
    <section class="stat-block stat-block--rose">
      <div class="stat-head">
        <div class="stat-title-group">
          <div class="panel-kicker">装置监测</div>
          <div class="panel-title">导管风险热力图</div>
        </div>
        <div class="panel-scale">装置风险分层</div>
      </div>
      <div class="chart-wrap chart-wrap-heatmap">
        <BigScreenChart :option="deviceHeatmapOption" :init-options="chartInitOptions" autoresize />
      </div>
    </section>
  </aside>
</template>

<script setup lang="ts">
import { defineAsyncComponent } from 'vue'
import { chartInitOptions as createChartInitOptions } from '../../charts/displayQuality'

defineProps<{
  deptOption: any
  bundleOption: any
  alertTrendOption: any
  deviceHeatmapOption: any
}>()

const BigScreenChart = defineAsyncComponent(async () => {
  await import('../../charts/bigscreen')
  const mod = await import('vue-echarts')
  return mod.default
})

const chartInitOptions = createChartInitOptions()
</script>

<style scoped>
.panel-right {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.stat-block {
  position: relative;
  padding: 12px;
  border-radius: var(--radius-lg);
  background: rgba(8, 23, 38, 0.96);
  border: 1px solid rgba(80, 199, 255, 0.12);
  box-shadow: var(--shadow-lg);
}
.stat-block::before {
  content: '';
  position: absolute;
  inset: 0 auto 0 0;
  width: 4px;
  border-radius: var(--radius-lg) 0 0 var(--radius-lg);
  background: rgba(34, 211, 238, 0.8);
}
.stat-block::after {
  content: '';
  position: absolute;
  top: 14px;
  right: 14px;
  width: 48px;
  height: 1px;
  background: rgba(103, 232, 249, 0.32);
}
.stat-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding-bottom: 10px;
  margin-bottom: 10px;
  border-bottom: 1px solid rgba(80, 199, 255, 0.08);
}
.stat-title-group {
  display: grid;
  gap: 3px;
  min-width: 0;
}
.panel-kicker {
  color: var(--color-text-tertiary);
  font-size: 9px;
  letter-spacing: .08em;
}
.panel-title {
  font-size: 13px;
  color: var(--color-text-inverse);
  letter-spacing: .04em;
  font-weight: 700;
}
.panel-scale {
  font-variant-numeric: tabular-nums;
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  padding: 0 9px;
  border-radius: 999px;
  background: rgba(9, 35, 52, 0.78);
  border: 1px solid rgba(80, 199, 255, 0.1);
  color: var(--color-text-tertiary);
  font-size: 10px;
  letter-spacing: .04em;
  white-space: nowrap;
}
.stat-block--green::before {
  background: rgba(74, 222, 128, 0.82);
}
.stat-block--amber::before {
  background: rgba(251, 191, 36, 0.84);
}
.stat-block--rose::before {
  background: rgba(251, 113, 133, 0.86);
}
.chart-wrap {
  position: relative;
  height: 240px;
  padding: 4px 2px 0;
  border-radius: var(--radius-lg);
  background: rgba(7, 20, 31, 0.48);
}
.chart-wrap-heatmap {
  height: 300px;
}
.chart-wrap :deep(canvas) {
  border-radius: 10px;
}
html[data-theme='light'] .stat-block {
  border-color: rgba(0, 0, 0, 0.06);
  background: var(--color-bg-surface);
  box-shadow: var(--shadow-sm);
}
html[data-theme='light'] .stat-block::after {
  display: none;
}
html[data-theme='light'] .stat-block--cyan::before { background: var(--color-primary); }
html[data-theme='light'] .stat-block--green::before { background: var(--color-success); }
html[data-theme='light'] .stat-block--amber::before { background: var(--color-warning); }
html[data-theme='light'] .stat-block--rose::before { background: var(--color-danger); }
html[data-theme='light'] .stat-head {
  border-bottom-color: rgba(0, 0, 0, 0.06);
}
html[data-theme='light'] .panel-kicker,
html[data-theme='light'] .panel-scale { color: var(--color-text-secondary); }
html[data-theme='light'] .panel-title { color: var(--color-text-primary); }
html[data-theme='light'] .panel-scale {
  border-color: rgba(0, 0, 0, 0.06);
  background: var(--color-bg-surface-secondary);
}
html[data-theme='light'] .chart-wrap {
  background: var(--color-bg-surface-secondary);
  border: 1px solid rgba(0, 0, 0, 0.04);
}

@media (max-width: 1100px) {
  .chart-wrap {
    height: 220px;
  }
  .chart-wrap-heatmap {
    height: 260px;
  }}</style>
