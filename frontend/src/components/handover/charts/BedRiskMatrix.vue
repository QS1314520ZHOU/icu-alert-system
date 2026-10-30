<template>
  <div class="bed-risk-matrix">
    <div class="matrix-header">
      <h3 class="matrix-title">床位风险矩阵</h3>
      <div class="matrix-legend">
        <span class="legend-item"><span class="dot dot--critical"></span>危急</span>
        <span class="legend-item"><span class="dot dot--high"></span>高危</span>
        <span class="legend-item"><span class="dot dot--medium"></span>中危</span>
        <span class="legend-item"><span class="dot dot--stable"></span>平稳</span>
        <span class="legend-item"><span class="dot dot--nodata"></span>无数据</span>
      </div>
    </div>
    <div class="matrix-grid">
      <div
        v-for="bed in beds"
        :key="bed.patient_id"
        class="bed-cell"
        :class="cellClass(bed)"
        @click="$emit('select', bed)"
      >
        <div class="bed-number">{{ bed.bed || '?' }}</div>
        <div class="bed-name">{{ bed.name || '空床' }}</div>
        <div class="bed-icons">
          <span v-if="bed.has_ventilator" class="icon-tag icon-tag--vent" title="呼吸机">机</span>
          <span v-if="bed.has_vasoactive" class="icon-tag icon-tag--vaso" title="血管活性药">升压</span>
          <span v-if="bed.has_crrt" class="icon-tag icon-tag--crrt" title="CRRT">CRRT</span>
          <span v-if="bed.unclosed_alert_count && bed.unclosed_alert_count > 0" class="icon-tag icon-tag--alert" :title="`${bed.unclosed_alert_count}条未闭环告警`">警 {{ bed.unclosed_alert_count }}</span>
        </div>
        <div class="bed-status">{{ handoverStatusLabel(bed.handover_status) }}</div>
      </div>
    </div>
    <div class="matrix-caption">
      该矩阵展示当前班次所有在科患者的交班优先级。
      数据范围：{{ timeRange }}；更新时间：{{ updatedAt }}
    </div>
  </div>
</template>

<script setup lang="ts">

interface BedPatient {
  patient_id: string
  bed: string
  name: string
  is_critical?: boolean
  has_ventilator?: boolean
  has_vasoactive?: boolean
  has_crrt?: boolean
  unclosed_alert_count?: number
  handover_status?: string
  risk_level?: string
}

const props = defineProps<{
  beds: BedPatient[]
  timeRange?: string
  updatedAt?: string
}>()

defineEmits<{ select: [bed: BedPatient] }>()

// 优先使用后端 risk_level（与交班重点患者同一口径）；缺失时再按字段推断
function cellClass(bed: BedPatient) {
  if (!bed.name) return 'bed-cell--nodata'
  const lv = String(bed.risk_level || '')
  if (lv === 'critical' || bed.is_critical) return 'bed-cell--critical'
  if (lv === 'high') return 'bed-cell--high'
  if (lv === 'medium') return 'bed-cell--medium'
  if (lv === 'stable') return 'bed-cell--stable'
  if (bed.has_vasoactive || (bed.unclosed_alert_count && bed.unclosed_alert_count > 0)) return 'bed-cell--high'
  if (bed.has_ventilator) return 'bed-cell--medium'
  return 'bed-cell--stable'
}

function handoverStatusLabel(status?: string) {
  const map: Record<string, string> = {
    draft: '草稿',
    submitted: '已提交',
    acknowledged: '已签收',
    not_created: '未创建',
  }
  return map[status || ''] || ''
}
</script>

<style scoped>
.bed-risk-matrix {
  background: var(--color-bg-surface);
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border);
  padding: 16px;
}
.matrix-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.matrix-title { font-size: 14px; font-weight: 600; color: var(--color-text-primary); margin: 0; }
.matrix-legend { display: flex; gap: 12px; font-size: 12px; color: var(--color-text-secondary); }
.legend-item { display: flex; align-items: center; gap: 4px; }
.dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.dot--critical { background: var(--color-danger); }
.dot--high { background: var(--color-high-risk); }
.dot--medium { background: var(--color-warning-soft); }
.dot--stable { background: var(--color-normal); }
.dot--nodata { background: var(--color-unknown); }

.matrix-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 8px;
}
.bed-cell {
  border: 2px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: 8px;
  cursor: pointer;
  transition: border-color 0.2s, box-shadow 0.2s;
  min-height: 80px;
}
.bed-cell:hover { box-shadow: var(--card-shadow); }
.bed-cell--critical { border-color: var(--color-danger); background: var(--color-danger-bg); }
.bed-cell--high { border-color: var(--color-high-risk); background: var(--color-warning-bg); }
.bed-cell--medium { border-color: var(--color-warning-soft); background: var(--color-warning-soft-bg); }
.bed-cell--stable { border-color: var(--color-normal); background: var(--color-normal-bg); }
.bed-cell--nodata { border-color: var(--color-unknown); background: var(--color-bg-page); }

.bed-number { font-size: 12px; font-weight: 600; color: var(--color-text-primary); }
.bed-name { font-size: 12px; color: var(--color-text-secondary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.bed-icons { display: flex; gap: 4px; margin-top: 4px; }
.icon-tag {
  font-size: 10px; font-weight: 600; padding: 1px 4px; border-radius: 3px;
  line-height: 1.2;
}
.icon-tag--vent { background: var(--color-info-bg); color: var(--color-info); }
.icon-tag--vaso { background: var(--color-danger-bg); color: var(--color-danger); }
.icon-tag--crrt { background: var(--color-ai-light); color: var(--color-ai); }
.icon-tag--alert { background: var(--color-danger-bg); color: var(--color-danger); }
.bed-status { font-size: 10px; color: var(--color-text-tertiary); margin-top: 4px; }

.matrix-caption { font-size: 12px; color: var(--color-text-tertiary); margin-top: 12px; border-top: 1px solid var(--color-divider); padding-top: 8px; }
</style>
