<template>
  <aside class="panel panel-right">
    <section class="stat-block">
      <div class="stat-head">
        <div class="panel-title">科室统计</div>
        <div class="panel-scale">ZONE / OCCUPANCY</div>
      </div>
      <div class="chart-wrap">
        <BigScreenChart :option="deptOption" autoresize />
      </div>
    </section>
    <section class="stat-block">
      <div class="stat-head">
        <div class="panel-title">Bundle 合规率</div>
        <div class="panel-scale">CARE / BUNDLE</div>
      </div>
      <div class="chart-wrap">
        <BigScreenChart :option="bundleOption" autoresize />
      </div>
    </section>
    <section class="stat-block">
      <div class="stat-head">
        <div class="panel-title">近24小时预警趋势</div>
        <div class="panel-scale">TREND / 24H</div>
      </div>
      <div class="chart-wrap">
        <BigScreenChart :option="alertTrendOption" autoresize />
      </div>
    </section>
    <section class="stat-block">
      <div class="stat-head">
        <div class="panel-title">导管风险热力图</div>
        <div class="panel-scale">DEVICE / RISK</div>
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
  gap: 12px;
}
.stat-block {
  position: relative;
  padding: 10px;
  border-radius: 12px;
  background:
    radial-gradient(circle at top, rgba(34, 211, 238, 0.06), rgba(34, 211, 238, 0) 32%),
    linear-gradient(180deg, rgba(7,20,34,.94) 0%, rgba(4,12,22,.96) 100%);
  border: 1px solid rgba(80, 199, 255, 0.12);
  box-shadow: inset 0 1px 0 rgba(145,228,255,.04);
}
.stat-block::before {
  content: '';
  position: absolute;
  top: 10px;
  right: 10px;
  width: 44px;
  height: 1px;
  background: linear-gradient(90deg, rgba(103,232,249,.36), rgba(103,232,249,0));
}
.stat-block::after {
  content: '';
  position: absolute;
  left: 10px;
  bottom: 10px;
  width: 32px;
  height: 1px;
  background: linear-gradient(90deg, rgba(103,232,249,.24), rgba(103,232,249,0));
}
.stat-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.panel-title {
  font-size: 12px;
  color: #67e8f9;
  margin-bottom: 8px;
  letter-spacing: .12em;
  text-transform: uppercase;
  border-bottom: 1px solid rgba(80,199,255,.08);
  padding-bottom: 8px;
}
.panel-scale {
  margin-bottom: 8px;
  color: #6ea9bc;
  font-size: 10px;
  letter-spacing: .12em;
  white-space: nowrap;
}
.chart-wrap {
  height: 240px;
}
.chart-wrap-heatmap {
  height: 300px;
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
