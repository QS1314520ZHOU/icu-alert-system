<template>
  <div class="detail-tab labs-tab">
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

<style scoped>
.detail-tab {
  display: grid;
  gap: 12px;
}
.labs-tab :deep(.ant-timeline-item-tail) {
  border-inline-start-color: rgba(80,199,255,.16);
}
.labs-tab :deep(.ant-timeline-item-head) {
  background: #16b3c9;
  border-color: rgba(110,231,249,.4);
  box-shadow: 0 0 10px rgba(34,211,238,.18);
}
.labs-tab :deep(.ant-timeline-item-content) {
  padding-bottom: 14px;
}
.lab-head {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
  color: #dffbff;
  margin-bottom: 8px;
}
.lab-head strong {
  font-size: 14px;
  color: #effcff;
}
.lab-head span {
  color: #7ecce1;
  font-size: 12px;
}
.lab-items {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.lab-item {
  font-size: 11px;
  padding: 4px 8px;
  border-radius: 8px;
  background: rgba(8,28,44,.78);
  color: #ccefff;
  border: 1px solid rgba(80,199,255,.12);
}
.lab-item.lab-high {
  color: #ffb1bd;
  background: rgba(70,16,28,.92);
  border-color: rgba(248,113,113,.24);
}
.lab-item.lab-low {
  color: #8cdfff;
  background: rgba(7,45,76,.9);
  border-color: rgba(56,189,248,.24);
}
.acid-base-card {
  margin-top: 10px;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid rgba(80,199,255,.14);
  background: linear-gradient(180deg, rgba(10,28,45,.78) 0%, rgba(8,19,32,.82) 100%);
}
.acid-base-head,
.acid-base-summary,
.acid-base-metrics,
.acid-base-components {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
}
.acid-base-head {
  justify-content: space-between;
  margin-bottom: 6px;
  color: #dffbff;
}
.acid-base-summary {
  margin-bottom: 6px;
}
.acid-pill,
.acid-comp {
  display: inline-flex;
  align-items: center;
  padding: 3px 8px;
  border-radius: 999px;
  font-size: 11px;
}
.acid-primary { background: rgba(14,165,183,.16); color: #7de8f6; }
.acid-secondary { background: rgba(245,158,11,.16); color: #fcd34d; }
.acid-tertiary { background: rgba(239,68,68,.16); color: #fda4af; }
.acid-base-metrics { color: #9fd3e2; font-size: 11px; margin-bottom: 6px; }
.acid-comp { background: rgba(148,163,184,.12); color: #dffbff; }
.acid-comp.abnormal { background: rgba(239,68,68,.18); color: #fca5a5; }
.tab-empty {
  color: #7ccfe4;
  font-size: 12px;
  padding: 12px;
  border-radius: 10px;
  background: rgba(8,28,44,.58);
  border: 1px dashed rgba(80,199,255,.14);
}
</style>
