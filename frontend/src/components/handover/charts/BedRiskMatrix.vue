<template>
  <div class="bed-risk-matrix">
    <div class="matrix-header">
      <h3 class="matrix-title">床位风险矩阵</h3>
      <div class="matrix-legend">
        <span class="legend-item"><span class="dot dot--critical"></span>危急</span>
        <span class="legend-item"><span class="dot dot--high"></span>高风险</span>
        <span class="legend-item"><span class="dot dot--medium"></span>提醒</span>
        <span class="legend-item"><span class="dot dot--stable"></span>稳定</span>
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
          <span v-if="bed.has_ventilator" class="icon-tag icon-tag--vent" title="呼吸机">V</span>
          <span v-if="bed.has_vasoactive" class="icon-tag icon-tag--vaso" title="血管活性药">P</span>
          <span v-if="bed.has_crrt" class="icon-tag icon-tag--crrt" title="CRRT">C</span>
          <span v-if="bed.unclosed_alert_count && bed.unclosed_alert_count > 0" class="icon-tag icon-tag--alert" :title="`${bed.unclosed_alert_count}条未闭环告警`">{{ bed.unclosed_alert_count }}</span>
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

function cellClass(bed: BedPatient) {
  if (bed.is_critical || bed.risk_level === 'critical') return 'bed-cell--critical'
  if (bed.has_vasoactive || bed.risk_level === 'high') return 'bed-cell--high'
  if (bed.unclosed_alert_count && bed.unclosed_alert_count > 0) return 'bed-cell--medium'
  if (!bed.name) return 'bed-cell--nodata'
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
  background: #fff;
  border-radius: 8px;
  border: 1px solid #DCE5EF;
  padding: 16px;
}
.matrix-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.matrix-title { font-size: 14px; font-weight: 600; color: #17233D; margin: 0; }
.matrix-legend { display: flex; gap: 12px; font-size: 12px; color: #5F6B7A; }
.legend-item { display: flex; align-items: center; gap: 4px; }
.dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.dot--critical { background: #D92D20; }
.dot--high { background: #F79009; }
.dot--medium { background: #E5B700; }
.dot--stable { background: #12A66A; }
.dot--nodata { background: #98A2B3; }

.matrix-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 8px;
}
.bed-cell {
  border: 2px solid #DCE5EF;
  border-radius: 6px;
  padding: 8px;
  cursor: pointer;
  transition: border-color 0.2s, box-shadow 0.2s;
  min-height: 80px;
}
.bed-cell:hover { box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
.bed-cell--critical { border-color: #D92D20; background: #FEF3F2; }
.bed-cell--high { border-color: #F79009; background: #FFFAEB; }
.bed-cell--medium { border-color: #E5B700; background: #FEFBE8; }
.bed-cell--stable { border-color: #12A66A; background: #ECFDF3; }
.bed-cell--nodata { border-color: #98A2B3; background: #F9FAFB; }

.bed-number { font-size: 12px; font-weight: 600; color: #17233D; }
.bed-name { font-size: 12px; color: #5F6B7A; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.bed-icons { display: flex; gap: 4px; margin-top: 4px; }
.icon-tag {
  font-size: 10px; font-weight: 600; padding: 1px 4px; border-radius: 3px;
  line-height: 1.2;
}
.icon-tag--vent { background: #E6F4FF; color: #2E90FA; }
.icon-tag--vaso { background: #FEF3F2; color: #D92D20; }
.icon-tag--crrt { background: #F4F0FF; color: #7A5AF8; }
.icon-tag--alert { background: #FEF3F2; color: #D92D20; }
.bed-status { font-size: 10px; color: #8A94A6; margin-top: 4px; }

.matrix-caption { font-size: 12px; color: #8A94A6; margin-top: 12px; border-top: 1px solid #F0F3F7; padding-top: 8px; }
</style>
