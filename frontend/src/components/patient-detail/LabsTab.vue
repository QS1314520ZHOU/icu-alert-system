<template>
  <div>
    <a-timeline>
      <a-timeline-item v-for="exam in labs" :key="exam.requestId">
        <div class="lab-head">
          <strong>{{ exam.examName || exam.requestName || '检验' }}</strong>
          <span>{{ fmtTime(exam.requestTime) }}</span>
        </div>
        <div class="lab-items">
          <span
            v-for="item in exam.items || []"
            :key="item.itemId || item.itemCode || item.itemName"
            :class="['lab-item', labFlag(item)]"
          >
            {{ item.itemName || item.itemCnName || '指标' }}:
            {{ item.result || item.resultValue || item.value }}
            {{ item.unit || '' }}
          </span>
        </div>
        <div v-if="exam.acidBaseInterpretation" class="acid-base-card">
          <div class="acid-base-head">
            <strong>血气自动解读</strong>
            <span>{{ exam.acidBaseInterpretation.compensation || '—' }}</span>
          </div>
          <div class="acid-base-summary">
            <span class="acid-pill acid-primary">{{ exam.acidBaseInterpretation.primary }}</span>
            <span v-if="exam.acidBaseInterpretation.secondary" class="acid-pill acid-secondary">{{ exam.acidBaseInterpretation.secondary }}</span>
            <span v-if="exam.acidBaseInterpretation.tertiary" class="acid-pill acid-tertiary">{{ exam.acidBaseInterpretation.tertiary }}</span>
          </div>
          <div class="acid-base-metrics">
            <span>AG {{ exam.acidBaseInterpretation.AG ?? '—' }}</span>
            <span>校正AG {{ exam.acidBaseInterpretation.corrected_AG ?? '—' }}</span>
            <span>Δ比 {{ exam.acidBaseInterpretation.delta_ratio ?? '—' }}</span>
          </div>
          <div v-if="exam.acidBaseInterpretation.abnormal_components?.length" class="acid-base-components">
            <span
              v-for="comp in exam.acidBaseInterpretation.abnormal_components"
              :key="comp.field"
              :class="['acid-comp', { abnormal: comp.abnormal }]"
            >
              {{ comp.field }} {{ comp.value ?? '—' }}{{ comp.unit || '' }}
            </span>
          </div>
        </div>
      </a-timeline-item>
    </a-timeline>
    <div v-if="!labs.length" class="tab-empty">暂无检验记录</div>
  </div>
</template>

<script setup lang="ts">
import { Timeline as ATimeline, TimelineItem as ATimelineItem } from 'ant-design-vue'

defineProps<{
  labs: any[]
  fmtTime: (v: any) => string
  labFlag: (item: any) => string
}>()
</script>
