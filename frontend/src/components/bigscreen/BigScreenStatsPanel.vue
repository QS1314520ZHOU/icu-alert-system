<template>
  <aside class="panel panel-right">
    <div class="panel-title">科室统计</div>
    <div class="chart-wrap">
      <BigScreenChart :option="deptOption" autoresize />
    </div>
    <div class="panel-title">Bundle 合规率</div>
    <div class="chart-wrap">
      <BigScreenChart :option="bundleOption" autoresize />
    </div>
    <div class="panel-title">近24小时预警趋势</div>
    <div class="chart-wrap">
      <BigScreenChart :option="alertTrendOption" autoresize />
    </div>
    <div class="panel-title">导管风险热力图</div>
    <div class="chart-wrap chart-wrap-heatmap">
      <BigScreenChart :option="deviceHeatmapOption" autoresize />
    </div>
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
.chart-wrap {
  height: 240px;
  margin-bottom: 12px;
}
.chart-wrap-heatmap {
  height: 300px;
}
</style>
