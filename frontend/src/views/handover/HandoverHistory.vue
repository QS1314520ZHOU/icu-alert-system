<template>
  <div class="handover-history">
    <header class="hh-header">
      <div>
        <h1 class="hh-title">交班历史</h1>
        <p class="hh-subtitle">按班次回溯病区交班总结：当时的在科人数、危重人数、未闭环项与交班完成情况</p>
      </div>
      <a-button :loading="loading" @click="load">刷新</a-button>
    </header>

    <a-alert v-if="error" type="error" show-icon :message="error" class="hh-block" />

    <a-table
      :data-source="items"
      :columns="columns"
      :loading="loading"
      size="small"
      row-key="summary_id"
      :pagination="{ pageSize: 15, hideOnSinglePage: true }"
      :expanded-row-keys="expandedKeys"
      @expand="onExpand"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'shift'">
          <div class="hh-shift">{{ record.shift_name || record.shift_code || '—' }}</div>
          <div class="hh-muted">{{ formatDateTime(record.scheduled_start) }} — {{ formatDateTime(record.scheduled_end) }}</div>
        </template>
        <template v-else-if="column.key === 'census'">
          {{ record.patient_count }} 人
          <span v-if="record.critical_patient_count" class="hh-critical">（危重 {{ record.critical_patient_count }}）</span>
        </template>
        <template v-else-if="column.key === 'support'">
          <span class="hh-muted">呼吸机 {{ record.ventilator_patient_count }} · 血管活性 {{ record.vasoactive_patient_count }} · CRRT {{ record.crrt_patient_count }}</span>
        </template>
        <template v-else-if="column.key === 'alerts'">
          <span :class="{ 'hh-critical': record.critical_value_count }">危急值 {{ record.critical_value_count }}</span>
          <span class="hh-sep">/</span>
          <span :class="{ 'hh-warning': record.unclosed_alert_count }">未闭环 {{ record.unclosed_alert_count }}</span>
        </template>
        <template v-else-if="column.key === 'progress'">
          <a-progress
            :percent="completion(record)"
            size="small"
            :status="completion(record) >= 100 ? 'success' : 'normal'"
            :format="() => `${record.acknowledged_patient_count}/${record.patient_count} 签收`"
          />
        </template>
        <template v-else-if="column.key === 'created'">
          <div>{{ formatDateTime(record.created_at) }}</div>
          <div v-if="record.created_by" class="hh-muted">{{ record.created_by }}</div>
        </template>
      </template>

      <template #expandedRowRender="{ record }">
        <a-spin :spinning="!!detailLoading[record.summary_id]">
          <div class="hh-detail">
            <p v-if="record.deterministic_summary" class="hh-summary">{{ record.deterministic_summary }}</p>
            <p v-if="record.ai_summary" class="hh-ai">AI 摘要：{{ record.ai_summary }}</p>
            <template v-if="details[record.summary_id]?.priority_items?.length">
              <h4 class="hh-h4">当班重点患者及原因</h4>
              <div v-for="p in details[record.summary_id].priority_items" :key="p.patient_id + p.reason" class="hh-prio">
                <a-tag :color="p.severity === 'critical' ? 'red' : p.severity === 'high' ? 'orange' : 'blue'">{{ p.bed || '—' }}</a-tag>
                <span class="hh-prio-name">{{ p.name }}</span>
                <span class="hh-muted">{{ p.reason }}</span>
              </div>
            </template>
            <p v-else-if="details[record.summary_id]" class="hh-muted">该班次无重点患者记录</p>
            <p class="hh-muted">数据窗口 {{ formatDateTime(record.data_start) }} — {{ formatDateTime(record.data_end) }} · 版本 {{ record.revision || 1 }}</p>
          </div>
        </a-spin>
      </template>
    </a-table>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { Alert as AAlert, Button as AButton, Progress as AProgress, Spin as ASpin, Table as ATable, Tag as ATag } from 'ant-design-vue'
import api from '../../api'
import { formatDateTime, useShiftSummary } from '../../composables/useShiftSummary'

const { deptCode } = useShiftSummary()
const loading = ref(false)
const error = ref('')
const items = ref<any[]>([])
const expandedKeys = ref<string[]>([])
const details = reactive<Record<string, any>>({})
const detailLoading = reactive<Record<string, boolean>>({})

const columns = [
  { title: '班次', key: 'shift', width: 200 },
  { title: '在科', key: 'census', width: 130 },
  { title: '生命支持', key: 'support' },
  { title: '危急值 / 未闭环', key: 'alerts', width: 170 },
  { title: '交班完成度', key: 'progress', width: 200 },
  { title: '生成时间', key: 'created', width: 120 },
]

function completion(r: any) {
  return r.patient_count ? Math.round((Number(r.acknowledged_patient_count || 0) / r.patient_count) * 100) : 0
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await api.get('/api/handover/shifts/history', { params: { dept_code: deptCode.value, limit: 60 } })
    items.value = res.data?.items || []
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || '加载交班历史失败'
  } finally {
    loading.value = false
  }
}

async function onExpand(expanded: boolean, record: any) {
  const id = record.summary_id
  expandedKeys.value = expanded ? [...expandedKeys.value, id] : expandedKeys.value.filter((k) => k !== id)
  if (!expanded || details[id]) return
  detailLoading[id] = true
  try {
    const res = await api.get(`/api/handover/shifts/${id}`)
    details[id] = res.data?.summary || {}
  } catch {
    details[id] = { priority_items: [] }
  } finally {
    detailLoading[id] = false
  }
}

onMounted(load)
</script>

<style scoped>
.handover-history { padding: var(--page-padding, 24px); max-width: 1400px; margin: 0 auto; width: 100%; }
.hh-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 16px; }
.hh-title { margin: 0; font-size: var(--text-page-title, 20px); font-weight: 600; color: var(--color-text-primary); }
.hh-subtitle { margin: 4px 0 0; font-size: var(--text-body, 13px); color: var(--color-text-secondary); }
.hh-block { margin-bottom: 12px; }
.hh-shift { font-weight: 600; color: var(--color-text-primary); }
.hh-muted { font-size: var(--text-caption, 12px); color: var(--color-text-tertiary); }
.hh-critical { color: var(--color-critical, #D92D20); font-weight: 600; }
.hh-warning { color: var(--color-warning, #B54708); font-weight: 600; }
.hh-sep { margin: 0 4px; color: var(--color-text-tertiary); }
.hh-detail { padding: 4px 8px; }
.hh-summary { margin: 0 0 8px; color: var(--color-text-primary); line-height: 1.6; }
.hh-ai { margin: 0 0 8px; color: var(--color-ai, #7C3AED); line-height: 1.6; }
.hh-h4 { margin: 8px 0 6px; font-size: var(--text-body, 13px); font-weight: 600; }
.hh-prio { display: flex; align-items: center; gap: 8px; padding: 3px 0; }
.hh-prio-name { font-weight: 600; min-width: 64px; }
</style>
