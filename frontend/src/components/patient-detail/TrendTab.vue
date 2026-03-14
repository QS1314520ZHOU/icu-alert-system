<template>
  <div>
    <div class="tab-toolbar">
      <a-radio-group :value="trendWindow" size="small" @update:value="(v: any) => emit('update:trendWindow', v)">
        <a-radio-button value="24h">24h</a-radio-button>
        <a-radio-button value="48h">48h</a-radio-button>
        <a-radio-button value="7d">7d</a-radio-button>
      </a-radio-group>
      <a-button size="small" @click="onRefresh">刷新</a-button>
    </div>
    <div v-if="trendPoints?.length" class="chart-wrap">
      <DetailChart :option="trendOption" autoresize />
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
