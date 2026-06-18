<template>
  <section class="priority-panel">
    <div class="priority-head">
      <div>
        <span>今日重点关注</span>
        <strong>{{ displayRows.length ? `重点关注前 ${displayRows.length} 位患者` : '暂无高优先级患者' }}</strong>
      </div>
      <small>{{ rows.length > displayRows.length ? `共 ${rows.length} 位高优先级，已优先展示最需要处理的 ${displayRows.length} 位` : '按风险闭环优先级排序' }}</small>
    </div>
    <div v-if="rows.length" class="priority-list">
      <button
        v-for="(item, idx) in displayRows"
        :key="item.patient_id"
        type="button"
        :class="['priority-row', `tone-${item.risk_level || 'unknown'}`]"
        @click="$emit('select', item.patient_id)"
      >
        <b>{{ idx + 1 }}</b>
        <div class="priority-main">
          <strong>{{ item.bed || '--' }}床 {{ item.name || '未知患者' }}</strong>
          <span>{{ compactReason(item) }}</span>
          <em>
            <i v-if="item.unhandled_alerts">{{ item.unhandled_alerts }} 未处理</i>
            <i v-if="item.new_alerts_6h">{{ item.new_alerts_6h }} 新发</i>
            <i v-if="item.mechanical_ventilation">机械通气</i>
            <i v-if="item.infection_risk">感染风险</i>
            <i v-if="item.data_missing">数据缺失</i>
          </em>
        </div>
        <div class="priority-side">
          <strong>{{ item.priority_score ?? 0 }}</strong>
          <span>{{ item.risk_trend === 'up' ? '↑ 上升' : '→ 平稳' }}</span>
        </div>
      </button>
    </div>
    <div v-else class="priority-empty">当前范围未发现需要置顶的闭环风险，仍需确认数据是否完整。</div>
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
  return text || '暂无明确风险原因'
}
</script>

<style scoped>
.priority-panel {
  display: grid;
  gap: 12px;
  padding: 14px;
  border: 1px solid rgba(80, 199, 255, 0.14);
  border-radius: 14px;
  background: linear-gradient(180deg, rgba(7, 20, 34, 0.9), rgba(4, 12, 22, 0.96));
}
.priority-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: end;
}
.priority-head div {
  display: grid;
  gap: 4px;
}
.priority-head span,
.priority-head small {
  color: #8cb7c9;
  font-size: 12px;
}
.priority-head strong {
  color: #ecfeff;
  font-size: 18px;
}
.priority-list {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}
.priority-row {
  display: grid;
  grid-template-columns: 26px minmax(0, 1fr) auto;
  gap: 8px;
  align-items: center;
  min-height: 88px;
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid rgba(125, 211, 252, 0.14);
  background: rgba(8, 28, 44, 0.72);
  color: #dffbff;
  text-align: left;
  cursor: pointer;
}
.priority-row > b {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border-radius: 999px;
  background: rgba(59, 130, 246, 0.22);
}
.priority-main {
  display: grid;
  gap: 6px;
  min-width: 0;
}
.priority-main strong {
  color: #f8feff;
  font-size: 14px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.priority-main span {
  color: #fcd34d;
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
  min-height: 22px;
}
.priority-main em i {
  padding: 2px 6px;
  border-radius: 999px;
  background: rgba(125, 211, 252, 0.1);
  color: #9bdcf5;
  font-size: 11px;
  font-style: normal;
  line-height: 1.35;
}
.priority-side {
  display: grid;
  gap: 2px;
  justify-items: end;
}
.priority-side strong {
  color: #fff;
  font-size: 22px;
  line-height: 1;
}
.priority-side span,
.priority-side small {
  color: #9cc2d1;
  font-size: 11px;
}
.tone-critical {
  border-color: rgba(248, 113, 113, 0.28);
  background: rgba(60, 14, 23, 0.42);
}
.tone-warning {
  border-color: rgba(245, 158, 11, 0.26);
  background: rgba(52, 34, 9, 0.36);
}
.priority-empty {
  color: #8cb7c9;
  padding: 12px;
  border: 1px dashed rgba(125, 211, 252, 0.18);
  border-radius: 12px;
}
html[data-theme='light'] .priority-panel,
html[data-theme='light'] .priority-row {
  border-color: rgba(187, 204, 220, 0.72);
  background: #fff;
}
html[data-theme='light'] .priority-head strong,
html[data-theme='light'] .priority-main strong,
html[data-theme='light'] .priority-side strong {
  color: #16324f;
}
html[data-theme='light'] .priority-head span,
html[data-theme='light'] .priority-head small,
html[data-theme='light'] .priority-main em,
html[data-theme='light'] .priority-side span,
html[data-theme='light'] .priority-side small {
  color: #64748b;
}
html[data-theme='light'] .priority-main em i {
  background: rgba(219, 234, 254, 0.9);
  color: #2563eb;
}
html[data-theme='light'] .priority-main span {
  color: #b45309;
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
