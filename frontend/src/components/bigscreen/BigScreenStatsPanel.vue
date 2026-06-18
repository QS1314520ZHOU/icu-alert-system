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
  border-radius: 4px;
  background: #FFFFFF;
  border: 1px solid rgba(80, 199, 255, 0.12);
  box-shadow:
    inset 0 1px 0 rgba(145, 228, 255, 0.04),
    0 16px 28px rgba(0, 0, 0, 0.18);
}
.stat-block::before {
  content: '';
  position: absolute;
  inset: 0 auto 0 0;
  width: 4px;
  border-radius: 4px 0 0 16px;
  background: #FFFFFF;
}
.stat-block::after {
  content: '';
  position: absolute;
  top: 14px;
  right: 14px;
  width: 48px;
  height: 1px;
  background: #FFFFFF;
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
  color: #6ea9bc;
  font-size: 9px;
  letter-spacing: .08em;
}
.panel-title {
  font-size: 13px;
  color: #dffbff;
  letter-spacing: .04em;
  font-weight: 700;
}
.panel-scale {
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  padding: 0 9px;
  border-radius: 999px;
  background: rgba(9, 35, 52, 0.78);
  border: 1px solid rgba(80, 199, 255, 0.1);
  color: #8fd4e6;
  font-size: 10px;
  letter-spacing: .04em;
  white-space: nowrap;
}
.stat-block--green::before {
  background: #FFFFFF;
}
.stat-block--amber::before {
  background: #FFFFFF;
}
.stat-block--rose::before {
  background: #FFFFFF;
}
.chart-wrap {
  position: relative;
  height: 240px;
  padding: 4px 2px 0;
  border-radius: 4px;
  background: #FFFFFF;
}
.chart-wrap-heatmap {
  height: 300px;
}
.chart-wrap :deep(canvas) {
  border-radius: 4px;
}
html[data-theme='light'] .stat-block {
  border-color: rgba(0, 0, 0, 0.06);
  background: #FFFFFF;
  box-shadow: 0 1px 3px rgba(0,0,0,0.04), 0 4px 12px rgba(0,0,0,0.03);
}
html[data-theme='light'] .stat-block::after {
  display: none;
}
html[data-theme='light'] .stat-block--cyan::before { background: #15558D; }
html[data-theme='light'] .stat-block--green::before { background: #22C55E; }
html[data-theme='light'] .stat-block--amber::before { background: #F59E0B; }
html[data-theme='light'] .stat-block--rose::before { background: #EF4444; }
html[data-theme='light'] .stat-head {
  border-bottom-color: rgba(0, 0, 0, 0.06);
}
html[data-theme='light'] .panel-kicker,
html[data-theme='light'] .panel-scale { color: #4E5969; }
html[data-theme='light'] .panel-title { color: #1D2129; }
html[data-theme='light'] .panel-scale {
  border-color: rgba(0, 0, 0, 0.06);
  background: #F1F5F9;
}
html[data-theme='light'] .chart-wrap {
  background: #F8FAFC;
  border: 1px solid rgba(0, 0, 0, 0.04);
}

@media (max-width: 1100px) {
  .chart-wrap {
    height: 220px;
  }
  .chart-wrap-heatmap {
    height: 260px;
  }
}
</style>
