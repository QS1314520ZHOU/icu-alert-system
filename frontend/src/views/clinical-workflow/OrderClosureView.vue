<template>
  <div class="order-closure">
    <!-- 医嘱闭环泳道 -->
    <section class="task-section">
      <div class="section-header">
        <span class="section-label info">医嘱闭环</span>
        <span class="section-count">{{ ctx.orderSwimlanes.value.length }}人</span>
      </div>
      <p class="section-hint">每床：告警 → 医嘱 → 执行 → 复查 → 结果</p>
      <div v-if="ctx.orderSwimlanes.value.length" class="swimlane-list">
        <button
          v-for="lane in ctx.orderSwimlanes.value"
          :key="`lane-${lane.patient_id}`"
          type="button"
          class="swimlane-row"
          @click="ctx.showVisualPatient(lane, 'order_gap')"
        >
          <strong>{{ lane.bed || '--' }}床</strong>
          <span
            v-for="step in lane.steps"
            :key="`${lane.patient_id}-${step.label}`"
            :class="`is-${step.status}`"
          >{{ step.label }}</span>
        </button>
      </div>
      <div v-else class="empty-hint">暂无闭环泳道</div>
    </section>

    <!-- 医嘱缺口 -->
    <section class="task-section">
      <div class="section-header">
        <span class="section-label warning">医嘱缺口</span>
        <span class="section-count">{{ ctx.doctorGaps.value.length }}项</span>
      </div>
      <div v-if="ctx.doctorGaps.value.length" class="gap-list">
        <div
          v-for="gap in ctx.doctorGaps.value.slice(0, 8)"
          :key="`${gap.patient_id}-${gap.gap_type}-${gap.title}`"
          class="gap-row"
        >
          <div class="gap-info">
            <strong>{{ gap.title }}</strong>
            <p>{{ gap.detail }}</p>
          </div>
          <button type="button" class="gap-action" @click="ctx.openRoundingSheet(gap.patient_id)">查房单</button>
        </div>
      </div>
      <div v-else class="empty-hint">暂无明确查房缺口</div>
    </section>

    <!-- 查房问题清单 -->
    <section v-if="roundingItems.length" class="task-section">
      <div class="section-header">
        <span class="section-label high">查房问题清单</span>
        <span class="section-count">{{ roundingItems.length }}项</span>
      </div>
      <div class="gap-list">
        <div
          v-for="item in roundingItems.slice(0, 6)"
          :key="`rounding-${item.patient_id}-${item.title}`"
          class="gap-row"
        >
          <div class="gap-info">
            <strong>{{ item.displayTitle || item.title }}</strong>
            <p>{{ item.detail }}</p>
          </div>
          <button type="button" class="gap-action" @click="runRounding(item)">查房</button>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ ctx: ReturnType<typeof import('../../composables/useClinicalWorkflow').useClinicalWorkflow> }>()

const roundingItems = computed(() => {
  const features = props.ctx.stickyFeatures.value || {}
  return (features.rounding_checklist || []).slice(0, 6)
})

function runRounding(item: any) {
  const patientId = String(item?.patient_id || props.ctx.firstPatientId() || '')
  if (patientId) props.ctx.openRoundingSheet(patientId)
}
</script>

<style scoped>
.order-closure {
  display: grid;
  gap: 16px;
}
.task-section {
  padding: 16px;
  border-radius: var(--card-radius);
  border: 1px solid var(--color-border);
  background: var(--bg-surface);
}
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.section-label {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary);
  padding: 3px 10px;
  border-radius: var(--card-radius);
}
.section-label.info { background: rgba(21,85,141,.15); color: var(--color-primary); }
.section-label.warning { background: rgba(232,144,28,.15); color: var(--color-warning); }
.section-label.high { background: rgba(251,146,60,.15); color: #b96b12; }
.section-count { font-size: 13px; color: var(--text-secondary); font-weight: 700; }
.section-hint { margin: 0 0 12px; font-size: 12px; color: var(--text-secondary); }

.swimlane-list { display: grid; gap: 6px; }
.swimlane-row {
  width: 100%;
  display: grid;
  grid-template-columns: 52px repeat(5, minmax(0, 1fr));
  gap: 6px;
  align-items: center;
  border: 1px solid var(--color-border);
  border-radius: var(--card-radius);
  padding: 8px;
  color: var(--text-primary);
  background: var(--color-primary-bg);
  cursor: pointer;
}
.swimlane-row:hover { border-color: rgba(103,232,249,.32); }
.swimlane-row strong { font-size: 12px; }
.swimlane-row span {
  padding: 5px 4px;
  border-radius: var(--card-radius);
  text-align: center;
  color: var(--text-secondary);
  background: var(--color-border);
  font-size: 11px;
}
.swimlane-row .is-done { color: var(--color-success); background: rgba(20,184,166,.22); }
.swimlane-row .is-todo { color: var(--color-warning); background: rgba(113,63,18,.28); }

.gap-list { display: grid; gap: 8px; }
.gap-row {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  padding: 12px;
  border: 1px solid var(--color-border);
  border-radius: var(--card-radius);
  background: var(--color-primary-bg);
}
.gap-info { flex: 1; min-width: 0; }
.gap-info strong { display: block; color: var(--text-primary); font-size: 13px; }
.gap-info p { margin: 4px 0 0; color: var(--text-secondary); font-size: 12px; line-height: 1.4; }
.gap-action {
  flex: 0 0 auto;
  border: 1px solid var(--color-border);
  border-radius: var(--card-radius);
  padding: 5px 10px;
  font-size: 12px;
  font-weight: 700;
  color: var(--accent);
  background: transparent;
  cursor: pointer;
}

.empty-hint {
  padding: 24px;
  text-align: center;
  color: var(--text-secondary);
  font-size: 13px;
}

@media (max-width: 1024px) {
  .swimlane-row {
    grid-template-columns: 44px repeat(5, minmax(0, 1fr));
    gap: 4px;
    padding: 6px;
  }
  .swimlane-row span { font-size: 10px; padding: 4px 2px; }
}
</style>
