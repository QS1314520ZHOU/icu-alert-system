<template>
  <section class="priority-panel">
    <div class="priority-head">
      <div>
        <span class="priority-head__label">重点关注</span>
        <strong class="priority-head__title">{{ displayRows.length ? `前 ${displayRows.length} 位` : '暂无' }}</strong>
      </div>
      <small v-if="rows.length > displayRows.length">共 {{ rows.length }} 位高优先级</small>
    </div>
    <div v-if="rows.length" class="priority-list">
      <button
        v-for="(item, idx) in displayRows"
        :key="item.patient_id"
        type="button"
        :class="['priority-row', `tone-${item.risk_level || 'unknown'}`]"
        @click="$emit('select', item.patient_id)"
      >
        <b class="priority-row__rank">{{ idx + 1 }}</b>
        <div class="priority-main">
          <strong>{{ item.bed || '--' }}床 {{ item.name || '未知' }}</strong>
          <span>{{ compactReason(item) }}</span>
          <em>
            <i v-if="item.unhandled_alerts">{{ item.unhandled_alerts }} 未处理</i>
            <i v-if="item.new_alerts_6h">{{ item.new_alerts_6h }} 新发</i>
            <i v-if="item.mechanical_ventilation">通气</i>
            <i v-if="item.infection_risk">感染</i>
            <i v-if="item.data_missing">数据缺失</i>
          </em>
        </div>
        <div class="priority-side">
          <strong>{{ item.priority_score ?? 0 }}</strong>
          <span>{{ item.risk_trend === 'up' ? '↑' : '→' }}</span>
        </div>
      </button>
    </div>
    <div v-else class="priority-empty">暂无高优先级患者</div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ rows: any[] }>()
defineEmits<{ (e: 'select', patientId: string): void }>()

const displayRows = computed(() => (props.rows || []).slice(0, 4))

function compactReason(item: any) {
  const reasons = Array.isArray(item?.risk_reasons) ? item.risk_reasons : []
  const text = reasons
    .slice(0, 2)
    .map((row: any) => String(row || '').replace(/\s+/g, '').trim())
    .filter(Boolean)
    .join(' · ')
  return text || '暂无明确风险'
}
</script>

<style scoped>
.priority-panel {
  display: grid;
  gap: 12px;
  padding: 16px;
  border: 1px solid var(--color-border, #E3E7EC);
  border-radius: var(--radius-lg, 8px);
  background: var(--color-bg-surface, #FFFFFF);
  margin-bottom: 16px;
}
.priority-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-end;
}
.priority-head div {
  display: grid;
  gap: 2px;
}
.priority-head__label {
  color: var(--color-text-secondary, #667085);
  font-size: 12px;
  font-weight: 500;
}
.priority-head__title {
  color: var(--text-main, #18212B);
  font-size: 15px;
  font-weight: 600;
}
.priority-head small {
  color: var(--color-text-secondary, #667085);
  font-size: 12px;
}
.priority-list {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}
.priority-row {
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr) auto;
  gap: 8px;
  align-items: center;
  min-height: 72px;
  padding: 10px 12px;
  border-radius: 6px;
  border: 1px solid var(--color-border, #E3E7EC);
  background: var(--color-bg-surface, #FFFFFF);
  color: var(--text-main, #18212B);
  text-align: left;
  cursor: pointer;
  transition: border-color 0.15s;
}
.priority-row:hover {
  border-color: var(--color-primary, #2563EB);
}
.priority-row__rank {
  display: grid;
  place-items: center;
  width: 24px;
  height: 24px;
  border-radius: 4px;
  background: var(--color-primary-bg, rgba(37, 99, 235, 0.08));
  color: var(--color-primary, #2563EB);
  font-size: 12px;
  font-weight: 600;
}
.priority-main {
  display: grid;
  gap: 4px;
  min-width: 0;
}
.priority-main strong {
  color: var(--text-main, #18212B);
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.priority-main span {
  color: var(--color-warning, #B54708);
  font-size: 12px;
  line-height: 1.35;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.priority-main em {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  font-style: normal;
}
.priority-main em i {
  padding: 1px 6px;
  border-radius: 3px;
  background: var(--color-bg-surface-secondary, #F1F3F5);
  color: var(--color-text-secondary, #667085);
  font-size: 12px;
  font-style: normal;
  line-height: 1.5;
}
.priority-side {
  display: grid;
  gap: 2px;
  justify-items: end;
}
.priority-side strong {
  font-family: 'Rajdhani', sans-serif;
  color: var(--text-main, #18212B);
  font-size: 20px;
  font-weight: 700;
  line-height: 1;
}
.priority-side span {
  color: var(--color-text-secondary, #667085);
  font-size: 12px;
}
.tone-critical {
  border-color: rgba(217, 45, 32, 0.25);
  border-left: 3px solid var(--color-danger, #D92D20);
}
.tone-warning {
  border-color: rgba(181, 71, 8, 0.2);
  border-left: 3px solid var(--color-warning, #B54708);
}
.priority-empty {
  color: var(--color-text-secondary, #667085);
  padding: 12px;
  border: 1px dashed var(--color-border, #E3E7EC);
  border-radius: 6px;
  font-size: 13px;
  text-align: center;
}
@media (max-width: 1280px) {
  .priority-list {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 720px) {
  .priority-head {
    align-items: start;
    flex-direction: column;
  }
  .priority-list {
    grid-template-columns: 1fr;
  }
}
</style>
