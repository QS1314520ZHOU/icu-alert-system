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
        <BigScreenChart :option="deptOption" autoresize />
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
        <BigScreenChart :option="bundleOption" autoresize />
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
        <BigScreenChart :option="alertTrendOption" autoresize />
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
        <BigScreenChart :option="deviceHeatmapOption" autoresize />
      </div>
    </section>
  </aside>
</template>

<script setup lang="ts">
import { defineAsyncComponent } from 'vue'

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
  border-radius: 16px;
  background:
    radial-gradient(circle at top, rgba(34, 211, 238, 0.08), rgba(34, 211, 238, 0) 34%),
    linear-gradient(180deg, rgba(8, 23, 38, 0.96) 0%, rgba(4, 12, 22, 0.98) 100%);
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
  border-radius: 16px 0 0 16px;
  background: linear-gradient(180deg, rgba(34, 211, 238, 0.8), rgba(8, 145, 178, 0.4));
}
.stat-block::after {
  content: '';
  position: absolute;
  top: 14px;
  right: 14px;
  width: 48px;
  height: 1px;
  background: linear-gradient(90deg, rgba(103, 232, 249, 0.32), rgba(103, 232, 249, 0));
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
  background: linear-gradient(180deg, rgba(74, 222, 128, 0.82), rgba(22, 163, 74, 0.42));
}
.stat-block--amber::before {
  background: linear-gradient(180deg, rgba(251, 191, 36, 0.84), rgba(245, 158, 11, 0.42));
}
.stat-block--rose::before {
  background: linear-gradient(180deg, rgba(251, 113, 133, 0.86), rgba(225, 29, 72, 0.4));
}
.chart-wrap {
  position: relative;
  height: 240px;
  padding: 4px 2px 0;
  border-radius: 12px;
  background: linear-gradient(180deg, rgba(7, 20, 31, 0.48) 0%, rgba(7, 20, 31, 0.14) 100%);
}
.chart-wrap-heatmap {
  height: 300px;
}
.chart-wrap :deep(canvas) {
  border-radius: 10px;
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
