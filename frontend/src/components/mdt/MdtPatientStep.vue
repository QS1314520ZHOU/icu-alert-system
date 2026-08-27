<template>
  <a-card :bordered="false" class="mdt-step-card">
    <div class="step-card__head">
      <div>
        <span class="step-kicker">第一步</span>
        <h2>选择患者与生成会诊</h2>
      </div>
      <a-button type="primary" :loading="loading" :disabled="!selectedPatientId" @click="$emit('generate')">
        生成 MDT 会诊
      </a-button>
    </div>

    <section class="patient-step-grid">
      <div class="patient-select-panel">
        <label>患者选择</label>
        <select :value="selectedPatientId" class="mdt-select" @change="$emit('update:selectedPatientId', ($event.target as HTMLSelectElement).value)">
          <option value="">选择患者</option>
          <option v-for="item in patientOptions" :key="item.value" :value="item.value">{{ item.label }}</option>
        </select>
        <div v-if="selectedPatientOutOfDeptHint" class="step-hint">{{ selectedPatientOutOfDeptHint }}</div>

        <div class="patient-brief">
          <strong>{{ patientHeadline }}</strong>
          <p>{{ patientSubline }}</p>
        </div>

        <div class="step-actions">
          <a-button :disabled="!selectedPatientId" @click="$emit('open-patient')">患者详情</a-button>
          <a-button type="primary" :disabled="!selectedPatientId" @click="$emit('next')">下一步</a-button>
        </div>
      </div>

      <div class="organ-panel">
        <div class="panel-title">
          <strong>七大系统风险</strong>
          <span>点击查看详情</span>
        </div>
        <OrganHeatmapFigure
          compact
          show-legend
          :organ-states="organStates"
          :organ-tooltips="organTooltips"
          @organ-click="$emit('organ-click', $event)"
        />
        <div class="organ-pill-grid">
          <button
            v-for="item in organRows"
            :key="item.agent"
            type="button"
            :class="['organ-pill', `is-${item.severity}`]"
            @click="$emit('organ-click', item.organKey)"
          >
            <span>{{ item.label }}</span>
            <b>{{ item.text }}</b>
          </button>
        </div>
      </div>
    </section>
  </a-card>
</template>

<script setup lang="ts">
import { Button as AButton, Card as ACard } from 'ant-design-vue'
import OrganHeatmapFigure from '../common/OrganHeatmapFigure.vue'

defineProps<{
  selectedPatientId: string
  patientOptions: Array<{ value: string; label: string }>
  patientHeadline: string
  patientSubline: string
  loading: boolean
  organRows: any[]
  organStates: Record<string, any>
  organTooltips: Record<string, any>
  selectedPatientOutOfDeptHint: string
}>()

defineEmits<{
  (event: 'update:selectedPatientId', value: string): void
  (event: 'generate'): void
  (event: 'open-patient'): void
  (event: 'organ-click', value: string): void
  (event: 'next'): void
}>()

void AButton
void ACard
</script>

<style scoped>
.mdt-step-card {
  border: 1px solid var(--border-color);
  border-radius: var(--card-radius);
  background: var(--bg-surface);
}
.step-card__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
}
.step-kicker {
  color: var(--brand);
  font-size: 12px;
  font-weight: 700;
}
h2 {
  margin: 4px 0 0;
  color: var(--text-primary);
  font-size: 18px;
}
.patient-step-grid {
  display: grid;
  grid-template-columns: minmax(280px, 0.82fr) minmax(380px, 1.18fr);
  gap: 14px;
  margin-top: 16px;
}
.patient-select-panel,
.organ-panel {
  padding: 16px;
  border: 1px solid var(--border-color);
  border-radius: var(--card-radius);
  background: var(--bg-surface);
}
label {
  display: block;
  margin-bottom: 6px;
  color: var(--text-secondary);
  font-size: 12px;
}
.mdt-select {
  width: 100%;
  min-height: 38px;
  border: 1px solid var(--border-color);
  border-radius: var(--card-radius);
  padding: 0 10px;
  color: var(--text-primary);
  background: var(--bg-surface);
  font-size: 13px;
}
.step-hint {
  margin-top: 6px;
  color: #f59e0b;
  font-size: 12px;
}
.patient-brief {
  margin: 14px 0;
  padding: 12px;
  border-radius: var(--card-radius);
  background: var(--bg-surface);
  border: 1px solid var(--border-color);
}
.patient-brief strong {
  display: block;
  color: var(--text-primary);
  font-size: 16px;
}
.patient-brief p {
  margin: 2px 0 0;
  color: var(--text-secondary);
  font-size: 12px;
}
.panel-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}
.panel-title strong {
  color: var(--text-primary);
  font-size: 14px;
}
.panel-title span {
  color: var(--text-secondary);
  font-size: 11px;
}
.step-actions {
  display: flex;
  gap: 8px;
  margin-top: 14px;
}
.organ-pill-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px;
  margin-top: 10px;
}
.organ-pill {
  display: flex;
  justify-content: space-between;
  align-items: center;
  min-height: 44px;
  padding: 8px 10px;
  border: 1px solid var(--border-color);
  border-radius: var(--card-radius);
  color: var(--text-secondary);
  text-align: left;
  background: var(--bg-surface);
  cursor: pointer;
  font-size: 12px;
}
.organ-pill span {
  color: var(--text-secondary);
}
.organ-pill b {
  color: var(--text-primary);
  font-weight: 600;
}
.organ-pill.is-critical,
.organ-pill.is-high {
  border-color: rgba(239, 68, 68, 0.3);
}
.organ-pill.is-critical b,
.organ-pill.is-high b {
  color: #ef4444;
}
.organ-pill.is-warning b {
  color: #f59e0b;
}
@media (max-width: 980px) {
  .patient-step-grid {
    grid-template-columns: 1fr;
  }
}
</style>
