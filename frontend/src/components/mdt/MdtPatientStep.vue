<template>
  <a-card :bordered="false" class="mdt-step-card">
    <div class="step-card__head">
      <div>
        <span class="step-kicker">第一步</span>
        <h2>选择患者与生成会诊</h2>
        <p>先确定本轮会诊对象，再生成七大系统风险简图和总控结果。</p>
      </div>
      <a-button type="primary" size="large" :loading="loading" :disabled="!selectedPatientId" @click="$emit('generate')">
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
          <span>患者基础信息</span>
          <strong>{{ patientHeadline }}</strong>
          <p>{{ patientSubline }}</p>
        </div>

        <div class="step-actions">
          <a-button :disabled="!selectedPatientId" @click="$emit('open-patient')">患者详情</a-button>
          <a-button type="primary" :disabled="!selectedPatientId" @click="$emit('next')">进入冲突评审</a-button>
        </div>
      </div>

      <div class="organ-panel">
        <div class="panel-title">
          <strong>七大系统风险简图</strong>
          <span>点击系统可在下一步查看专科意见</span>
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
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 4px;
  background: rgba(15, 23, 42, 0.66);
}
.step-card__head,
.panel-title,
.step-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
}
.step-kicker {
  color: rgba(125, 211, 252, 0.86);
  font-size: 12px;
  font-weight: 700;
}
h2 {
  margin: 4px 0 6px;
  color: #f8fafc;
}
p {
  margin: 0;
  color: rgba(203, 213, 225, 0.72);
}
.patient-step-grid {
  display: grid;
  grid-template-columns: minmax(280px, 0.82fr) minmax(380px, 1.18fr);
  gap: 14px;
  margin-top: 18px;
}
.patient-select-panel,
.organ-panel {
  padding: 16px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 4px;
  background: rgba(2, 6, 23, 0.26);
}
label {
  display: block;
  margin-bottom: 8px;
  color: rgba(226, 232, 240, 0.86);
}
.mdt-select {
  width: 100%;
  min-height: 42px;
  border: 1px solid rgba(148, 163, 184, 0.24);
  border-radius: 4px;
  padding: 0 12px;
  color: #f8fafc;
  background: #FFFFFF;
}
.step-hint {
  margin-top: 8px;
  color: #fed7aa;
}
.patient-brief {
  margin: 18px 0;
  padding: 14px;
  border-radius: 4px;
  background: rgba(30, 41, 59, 0.54);
}
.patient-brief span,
.panel-title span {
  color: rgba(148, 163, 184, 0.82);
}
.patient-brief strong,
.panel-title strong {
  display: block;
  color: #f8fafc;
  font-size: 18px;
}
.organ-pill-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin-top: 12px;
}
.organ-pill {
  min-height: 52px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 4px;
  color: #e2e8f0;
  text-align: left;
  background: rgba(15, 23, 42, 0.72);
  cursor: pointer;
}
.organ-pill span,
.organ-pill b {
  display: block;
  padding: 0 10px;
}
.organ-pill.is-critical,
.organ-pill.is-high {
  border-color: rgba(248, 113, 113, 0.46);
}
@media (max-width: 980px) {
  .patient-step-grid {
    grid-template-columns: 1fr;
  }
}

:global(html[data-theme='light']) .mdt-step-card,
:global(html[data-theme='light']) .patient-select-panel,
:global(html[data-theme='light']) .organ-panel {
  border-color: #dbeafe;
  background: #FFFFFF;
  box-shadow: 0 1px 2px rgba(0,0,0,.06);
}
:global(html[data-theme='light']) .step-kicker,
:global(html[data-theme='light']) .panel-title span {
  color: #0284c7;
}
:global(html[data-theme='light']) h2,
:global(html[data-theme='light']) .patient-brief strong,
:global(html[data-theme='light']) .panel-title strong {
  color: #1D2129;
}
:global(html[data-theme='light']) p,
:global(html[data-theme='light']) label,
:global(html[data-theme='light']) .patient-brief span {
  color: #4E5969;
}
:global(html[data-theme='light']) .mdt-select {
  color: #1D2129;
  border-color: #E5E6EB;
  background: #FFFFFF;
}
:global(html[data-theme='light']) .patient-brief,
:global(html[data-theme='light']) .organ-pill {
  border-color: #e2e8f0;
  background: #f8fafc;
}
:global(html[data-theme='light']) .organ-pill {
  color: #1D2129;
}
:global(html[data-theme='light']) .organ-pill b {
  color: #1D2129;
}
</style>
