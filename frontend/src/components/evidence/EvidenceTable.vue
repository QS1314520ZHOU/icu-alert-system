<template>
  <div class="evidence-table-wrap">
    <div v-if="!rows.length" class="table-empty">暂无原始证据数据</div>
    <div v-else class="table-container">
      <table class="evidence-table">
        <thead>
          <tr>
            <th>时间</th>
            <th>类别</th>
            <th>名称</th>
            <th>值</th>
            <th>单位</th>
            <th>参考范围</th>
            <th>状态</th>
            <th v-if="showSource">来源</th>
            <th>质量</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in displayRows" :key="row.record_id">
            <td class="col-time">{{ formatTime(row.observed_at) }}</td>
            <td class="col-category">{{ categoryLabel(row.category) }}</td>
            <td class="col-name">{{ row.name }}</td>
            <td :class="['col-value', `flag-${row.abnormal_flag}`]">{{ formatValue(row.value) }}</td>
            <td class="col-unit">{{ row.unit }}</td>
            <td class="col-range">{{ row.reference_range || '—' }}</td>
            <td class="col-flag">
              <span :class="['flag-tag', `flag-${row.abnormal_flag}`]">{{ flagLabel(row.abnormal_flag) }}</span>
            </td>
            <td v-if="showSource" class="col-source">{{ row.source_system || '—' }}</td>
            <td class="col-quality">{{ qualityLabel(row.data_quality) }}</td>
          </tr>
        </tbody>
      </table>
      <div v-if="rows.length > pageSize" class="table-pagination">
        <button :disabled="currentPage <= 1" @click="currentPage--">上一页</button>
        <span>{{ currentPage }} / {{ totalPages }}</span>
        <button :disabled="currentPage >= totalPages" @click="currentPage++">下一页</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { EvidenceRow } from '../../api/clinicalEvidence'

const props = withDefaults(defineProps<{
  rows: EvidenceRow[]
  showSource?: boolean
  pageSize?: number
}>(), {
  showSource: false,
  pageSize: 20,
})

const currentPage = ref(1)

const totalPages = computed(() => Math.ceil(props.rows.length / props.pageSize))

const displayRows = computed(() => {
  const start = (currentPage.value - 1) * props.pageSize
  return props.rows.slice(start, start + props.pageSize)
})

function formatTime(t: string | null): string {
  if (!t) return '—'
  const d = new Date(t)
  return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`
}

function formatValue(v: number | string | null | undefined): string {
  if (v == null) return '不可计算'
  if (typeof v === 'number') return Number.isInteger(v) ? String(v) : v.toFixed(1)
  return String(v)
}

function categoryLabel(cat: string): string {
  const map: Record<string, string> = {
    vital_sign: '生命体征', alert: '告警', medication: '用药',
    medication_execution: '用药执行', clinical_score: '评分',
    nursing: '护理', rule_stat: '规则统计', unclosed_alert: '未闭环',
  }
  return map[cat] || cat
}

function flagLabel(flag: string): string {
  const map: Record<string, string> = { critical: '危急', high: '偏高', low: '偏低', normal: '正常', missing: '缺失' }
  return map[flag] || flag
}

function qualityLabel(q: string): string {
  const map: Record<string, string> = { complete: '完整', partial: '部分', missing: '缺失' }
  return map[q] || q
}
</script>

<style scoped>
.table-container { overflow-x: auto; }
.evidence-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.evidence-table th {
  text-align: left;
  padding: 6px 8px;
  background: var(--bg-secondary, #F9FAFB);
  border-bottom: 1px solid var(--color-border, #E5E7EB);
  font-weight: 600;
  color: var(--text-secondary, #6B7280);
  white-space: nowrap;
}
.evidence-table td {
  padding: 6px 8px;
  border-bottom: 1px solid var(--color-border, #F3F4F6);
  color: var(--text-primary, #182230);
}
.col-time { white-space: nowrap; color: var(--text-tertiary, #9CA3AF); }
.col-value.flag-critical { color: #DC2626; font-weight: 700; }
.col-value.flag-high { color: #EA580C; font-weight: 600; }
.col-value.flag-low { color: #D97706; font-weight: 600; }
.flag-tag {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 4px;
  font-weight: 600;
}
.flag-tag.flag-critical { background: #DC2626; color: #fff; }
.flag-tag.flag-high { background: #EA580C; color: #fff; }
.flag-tag.flag-low { background: #D97706; color: #fff; }
.flag-tag.flag-normal { background: #DCFCE7; color: #166534; }
.flag-tag.flag-missing { background: #F3F4F6; color: #6B7280; }
.table-pagination {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 12px;
  padding: 8px 0;
  font-size: 12px;
}
.table-pagination button {
  padding: 2px 10px;
  border: 1px solid var(--color-border, #E5E7EB);
  border-radius: 4px;
  background: #fff;
  cursor: pointer;
  font-size: 12px;
}
.table-pagination button:disabled { opacity: 0.4; cursor: not-allowed; }
.table-empty {
  text-align: center;
  padding: 20px;
  color: var(--text-tertiary, #9CA3AF);
  font-size: 13px;
}
</style>
