<template>
  <div class="detail-tab trend-tab">
    <div class="tab-toolbar">
      <a-radio-group :value="trendWindow" size="small" @update:value="(v: any) => emit('update:trendWindow', v)">
        <a-radio-button value="24h">24h</a-radio-button>
        <a-radio-button value="48h">48h</a-radio-button>
        <a-radio-button value="7d">7d</a-radio-button>
      </a-radio-group>
      <a-button size="small" @click="onRefresh">刷新</a-button>
    </div>
    <div v-if="trendPoints?.length" class="chart-panel">
      <div class="chart-wrap">
      <DetailChart :option="trendOption" autoresize />
      </div>
    </div>
    <div v-else class="tab-empty">暂无趋势数据</div>
  </div>
</template>

<script setup lang="ts">
import { defineAsyncComponent } from 'vue'
import { Button as AButton, RadioButton as ARadioButton, RadioGroup as ARadioGroup } from 'ant-design-vue'

defineProps<{
  trendWindow: string
  trendPoints: any[]
  trendOption: any
  onRefresh: () => void
}>()

const emit = defineEmits<{
  (e: 'update:trendWindow', value: string): void
}>()

const DetailChart = defineAsyncComponent(async () => {
  await import('../../charts/patient-detail')
  const mod = await import('vue-echarts')
  return mod.default
})
</script>

<style scoped>
.detail-tab {
  display: grid;
  gap: 12px;
}
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.chart-panel {
  padding: 12px;
  border-radius: 12px;
  background: linear-gradient(180deg, rgba(7,20,34,.92) 0%, rgba(4,12,22,.94) 100%);
  border: 1px solid rgba(80,199,255,.12);
  box-shadow: inset 0 1px 0 rgba(145,228,255,.04);
}
.chart-wrap {
  height: 360px;
}
.tab-empty {
  color: #7ccfe4;
  font-size: 12px;
  padding: 12px;
  border-radius: 10px;
  background: rgba(8,28,44,.58);
  border: 1px dashed rgba(80,199,255,.14);
}
.trend-tab :deep(.ant-radio-group) {
  display: inline-flex;
  gap: 6px;
}
.trend-tab :deep(.ant-radio-button-wrapper) {
  border-radius: 10px !important;
  border: 1px solid rgba(80,199,255,.14) !important;
  background: rgba(8,28,44,.78) !important;
  color: #8bcfe1 !important;
}
.trend-tab :deep(.ant-radio-button-wrapper::before) {
  display: none !important;
}
.trend-tab :deep(.ant-radio-button-wrapper-checked) {
  background: linear-gradient(180deg, rgba(11,107,137,.96) 0%, rgba(7,63,86,.98) 100%) !important;
  color: #effcff !important;
  border-color: rgba(110,231,249,.28) !important;
}
.trend-tab :deep(.ant-btn) {
  background: rgba(8,28,44,.78);
  border-color: rgba(80,199,255,.14);
  color: #dffbff;
}
</style>
