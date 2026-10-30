<template>
  <div class="handover-patients">
    <header class="hp-header">
      <div>
        <h1 class="hp-title">患者交班</h1>
        <p class="hp-subtitle">
          {{ summary?.shift_name || '当前班次' }}
          <template v-if="summary">· 数据窗口 {{ formatDateTime(summary.data_start) }} — {{ formatDateTime(summary.data_end) }}</template>
        </p>
      </div>
      <a-button :loading="loading" @click="load">刷新</a-button>
    </header>

    <a-alert v-if="error" type="error" show-icon :message="error" class="hp-block" />

    <!-- 交班进度：先看还剩多少床没交 -->
    <section v-if="summary" class="hp-progress hp-block">
      <div class="hp-progress__bar">
        <div class="hp-progress__seg hp-progress__seg--ack" :style="{ width: pct(statusCount.acknowledged) }" />
        <div class="hp-progress__seg hp-progress__seg--sub" :style="{ width: pct(statusCount.submitted) }" />
        <div class="hp-progress__seg hp-progress__seg--draft" :style="{ width: pct(statusCount.draft + statusCount.returned) }" />
      </div>
      <div class="hp-progress__legend">
        <button
          v-for="s in statusFilters"
          :key="s.key"
          class="hp-chip"
          :class="{ 'hp-chip--active': statusFilter === s.key }"
          @click="statusFilter = statusFilter === s.key ? '' : s.key"
        >
          {{ s.label }} <b>{{ s.count }}</b>
        </button>
        <span class="hp-progress__total">共 {{ patients.length }} 床，已签收 {{ statusCount.acknowledged }}，剩余 {{ patients.length - statusCount.acknowledged }} 床待完成</span>
      </div>
    </section>

    <section v-if="summary" class="hp-filters hp-block">
      <a-input v-model:value="keyword" allow-clear placeholder="床号 / 姓名 / 诊断" style="width: 220px" />
      <a-radio-group v-model:value="riskFilter" size="small" button-style="solid">
        <a-radio-button value="">全部</a-radio-button>
        <a-radio-button v-for="(label, key) in RISK_LABELS" :key="key" :value="key">
          {{ label }} {{ riskCount[key] || 0 }}
        </a-radio-button>
      </a-radio-group>
      <a-checkbox v-model:checked="onlyLifeSupport">仅生命支持</a-checkbox>
      <span class="hp-rule" :title="riskRule">分级规则 ⓘ</span>
    </section>

    <a-table
      v-if="summary"
      :data-source="rows"
      :columns="columns"
      :loading="loading"
      size="small"
      row-key="patient_id"
      :pagination="false"
      :row-class-name="rowClass"
      class="hp-block"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'bed'">
          <span class="hp-bed">{{ record.bed || '—' }}</span>
        </template>
        <template v-else-if="column.key === 'patient'">
          <div class="hp-name">{{ record.name || '未命名' }}</div>
          <div class="hp-diag" :title="record.diagnosis">{{ record.diagnosis || '诊断未录入' }}</div>
        </template>
        <template v-else-if="column.key === 'risk'">
          <a-tag :color="RISK_COLORS[record.risk_level] || 'default'">{{ RISK_LABELS[record.risk_level] || record.risk_level }}</a-tag>
          <div class="hp-reasons">
            <span v-for="r in deriveRiskReasons(record as ShiftPatientStat)" :key="r" class="hp-reason">{{ r }}</span>
            <span v-if="!deriveRiskReasons(record as ShiftPatientStat).length" class="hp-muted">无触发项</span>
          </div>
        </template>
        <template v-else-if="column.key === 'support'">
          <div class="hp-support">
            <a-tag v-if="record.has_ventilator" color="blue">呼吸机</a-tag>
            <a-tag v-if="record.has_vasoactive" color="volcano">血管活性药</a-tag>
            <a-tag v-if="record.has_crrt" color="purple">CRRT</a-tag>
            <a-tag v-if="record.high_risk_line_count" color="orange">高危管路×{{ record.high_risk_line_count }}</a-tag>
            <a-tag v-if="isolationText(record.isolation)" color="magenta">{{ isolationText(record.isolation) }}</a-tag>
            <span v-if="!hasSupport(record)" class="hp-muted">—</span>
          </div>
        </template>
        <template v-else-if="column.key === 'alerts'">
          <div class="hp-alerts">
            <span :class="{ 'hp-num--critical': record.critical_value_count > 0 }">危急值 {{ record.critical_value_count }}</span>
            <span :class="{ 'hp-num--warning': record.unclosed_alert_count > 0 }">未闭环 {{ record.unclosed_alert_count }}</span>
            <span class="hp-muted">本班告警 {{ record.alert_count }}</span>
          </div>
        </template>
        <template v-else-if="column.key === 'status'">
          <a-tag :color="HANDOVER_STATUS_COLORS[statusOf(record)] || 'default'">
            {{ HANDOVER_STATUS_LABELS[statusOf(record)] || statusOf(record) }}
          </a-tag>
          <div v-if="record.handover_updated_at" class="hp-muted">{{ formatDateTime(record.handover_updated_at) }}</div>
        </template>
        <template v-else-if="column.key === 'action'">
          <a-button size="small" :type="statusOf(record) === 'not_started' ? 'primary' : 'default'" @click="openIsbar(record.patient_id)">
            {{ actionLabel(record) }}
          </a-button>
        </template>
      </template>
    </a-table>

    <a-empty v-if="!loading && !summary && !error" description="暂无当前班次数据" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  Alert as AAlert, Button as AButton, Checkbox as ACheckbox, Empty as AEmpty, Input as AInput,
  Radio as ARadio, Table as ATable, Tag as ATag,
} from 'ant-design-vue'
import {
  useShiftSummary, deriveRiskReasons, formatDateTime, RISK_LABELS, RISK_COLORS, RISK_ORDER,
  HANDOVER_STATUS_LABELS, HANDOVER_STATUS_COLORS, type ShiftPatientStat,
} from '../../composables/useShiftSummary'

const ARadioGroup = ARadio.Group
const ARadioButton = ARadio.Button

const router = useRouter()
const { loading, error, summary, patients, load } = useShiftSummary()

const keyword = ref('')
const riskFilter = ref('')
const statusFilter = ref('')
const onlyLifeSupport = ref(false)

const DEFAULT_RULE = '危急: 危急值>0 或 未闭环高危告警 或 (生命支持且未闭环告警>2)；高危: 血管活性药/CRRT/未闭环告警；中危: 机械通气/高危管路；其余为平稳'
const riskRule = computed(() => patients.value.find((p) => p.risk_rule)?.risk_rule || DEFAULT_RULE)

function statusOf(p: any): string {
  return p.handover_status || 'not_started'
}
function hasSupport(p: any) {
  return p.has_ventilator || p.has_vasoactive || p.has_crrt || p.high_risk_line_count > 0 || !!isolationText(p.isolation)
}

const statusCount = computed(() => {
  const c = { not_started: 0, draft: 0, submitted: 0, acknowledged: 0, returned: 0 } as Record<'not_started' | 'draft' | 'submitted' | 'acknowledged' | 'returned', number> & Record<string, number>
  for (const p of patients.value) c[statusOf(p)] = (c[statusOf(p)] || 0) + 1
  return c
})
const riskCount = computed(() => {
  const c: Record<string, number> = {}
  for (const p of patients.value) c[p.risk_level] = (c[p.risk_level] || 0) + 1
  return c
})
const statusFilters = computed(() => [
  { key: 'not_started', label: '未开始', count: statusCount.value.not_started },
  { key: 'draft', label: '草稿', count: statusCount.value.draft },
  { key: 'returned', label: '已退回', count: statusCount.value.returned },
  { key: 'submitted', label: '待签收', count: statusCount.value.submitted },
  { key: 'acknowledged', label: '已签收', count: statusCount.value.acknowledged },
])
function pct(n: number) {
  return patients.value.length ? `${(n / patients.value.length) * 100}%` : '0%'
}

const rows = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  return patients.value
    .filter((p) => !riskFilter.value || p.risk_level === riskFilter.value)
    .filter((p) => !statusFilter.value || statusOf(p) === statusFilter.value)
    .filter((p) => !onlyLifeSupport.value || p.has_ventilator || p.has_vasoactive || p.has_crrt)
    .filter((p) => !kw || `${p.bed} ${p.name} ${p.diagnosis}`.toLowerCase().includes(kw))
    .slice()
    // 先按风险，再按床号——交班时从最危重的床开始
    .sort((a, b) => (RISK_ORDER[a.risk_level] ?? 9) - (RISK_ORDER[b.risk_level] ?? 9)
      || String(a.bed).localeCompare(String(b.bed), 'zh-CN', { numeric: true }))
})

const columns = [
  { title: '床号', key: 'bed', width: 70 },
  { title: '患者 / 诊断', key: 'patient', width: 200 },
  { title: '风险等级与判定依据', key: 'risk' },
  { title: '生命支持 / 管路', key: 'support', width: 220 },
  { title: '告警', key: 'alerts', width: 110 },
  { title: '交班单', key: 'status', width: 100 },
  { title: '', key: 'action', width: 100 },
]

function rowClass(record: any) {
  return record.risk_level === 'critical' ? 'hp-row--critical' : ''
}
function actionLabel(p: any) {
  const s = statusOf(p)
  if (s === 'not_started') return '开始交班'
  if (s === 'draft' || s === 'returned') return '继续编辑'
  if (s === 'submitted') return '核对签收'
  return '查看'
}
function isolationText(v: unknown) {
  const t = String(v ?? '').trim()
  if (!t || ['false', '0', 'no', 'none', 'null'].includes(t.toLowerCase())) return ''
  if (['true', '1', 'yes', '隔离'].includes(t.toLowerCase())) return '隔离'
  return t.includes('隔离') ? t : `隔离:${t}`
}
function openIsbar(patientId: string) {
  router.push({ name: 'handover-patient', params: { patientId } })
}

onMounted(load)
</script>

<style scoped>
.handover-patients { padding: var(--page-padding, 24px); max-width: 1400px; margin: 0 auto; width: 100%; }
.hp-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 16px; }
.hp-title { margin: 0; font-size: var(--text-page-title, 20px); font-weight: 600; color: var(--color-text-primary); }
.hp-subtitle { margin: 4px 0 0; font-size: var(--text-body, 13px); color: var(--color-text-secondary); }
.hp-block { margin-bottom: 12px; }
.hp-progress { background: var(--color-bg-surface); border: 1px solid var(--color-border); border-radius: var(--radius-lg, 10px); padding: 12px 16px; }
.hp-progress__bar { display: flex; height: 8px; border-radius: 4px; background: var(--color-bg-inset); overflow: hidden; }
.hp-progress__seg--ack { background: var(--color-normal, #12A66A); }
.hp-progress__seg--sub { background: var(--color-primary, #2F6FED); }
.hp-progress__seg--draft { background: var(--color-warning, #B54708); }
.hp-progress__legend { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-top: 10px; }
.hp-progress__total { margin-left: auto; font-size: var(--text-caption, 12px); color: var(--color-text-secondary); }
.hp-chip { border: 1px solid var(--color-border); background: var(--color-bg-surface); border-radius: 999px; padding: 2px 10px; font-size: var(--text-caption, 12px); color: var(--color-text-secondary); cursor: pointer; }
.hp-chip--active { border-color: var(--color-primary); color: var(--color-primary); background: var(--color-primary-bg); }
.hp-filters { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; }
.hp-rule { font-size: var(--text-caption, 12px); color: var(--color-text-tertiary); cursor: help; margin-left: auto; }
.hp-bed { font-weight: 700; font-size: 15px; color: var(--color-text-primary); }
.hp-name { font-weight: 600; color: var(--color-text-primary); }
.hp-diag { font-size: var(--text-caption, 12px); color: var(--color-text-secondary); max-width: 190px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.hp-reasons { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 4px; }
.hp-reason { font-size: var(--text-caption, 12px); padding: 1px 6px; border-radius: var(--radius-tag, 4px); background: var(--color-bg-surface-secondary); color: var(--color-text-secondary); }
.hp-support { display: flex; flex-wrap: wrap; gap: 2px; }
.hp-alerts { display: flex; flex-direction: column; font-size: var(--text-caption, 12px); color: var(--color-text-secondary); }
.hp-num--critical { color: var(--color-critical, #D92D20); font-weight: 600; }
.hp-num--warning { color: var(--color-warning, #B54708); font-weight: 600; }
.hp-muted { font-size: var(--text-caption, 12px); color: var(--color-text-tertiary); }
:deep(.hp-row--critical) td:first-child { box-shadow: inset 3px 0 0 var(--color-critical, #D92D20); }
</style>
