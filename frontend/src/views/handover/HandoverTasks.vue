<template>
  <div class="handover-tasks">
    <header class="ht-header">
      <div>
        <h1 class="ht-title">待办与未闭环</h1>
        <p class="ht-subtitle">交班前必须逐条交代的危急值与未闭环告警（按床位分组，逐条列出原始记录）</p>
      </div>
      <a-button :loading="loading || detailLoading" @click="reload">刷新</a-button>
    </header>

    <a-alert v-if="error" type="error" show-icon :message="error" class="ht-block" />

    <div v-if="summary" class="ht-metrics ht-block">
      <div class="ht-metric ht-metric--critical"><b>{{ summary.critical_value_count }}</b><span>危急值</span></div>
      <div class="ht-metric ht-metric--warning"><b>{{ summary.unclosed_alert_count }}</b><span>未闭环告警</span></div>
      <div class="ht-metric"><b>{{ countOrNA(summary.pending_order_count, 'orders') }}</b><span>待执行医嘱</span></div>
      <div class="ht-metric"><b>{{ countOrNA(summary.pending_task_count, 'tasks') }}</b><span>待办任务</span></div>
      <div class="ht-metric ht-metric--warning"><b>{{ countOrNA(summary.overdue_task_count, 'tasks') }}</b><span>逾期任务</span></div>
      <div class="ht-metric"><b>{{ bedsWithItems.length }}</b><span>涉及床位</span></div>
    </div>

    <a-alert
      v-if="summary && sourceGaps.length"
      type="warning"
      show-icon
      class="ht-block"
      :message="`以下数据源未接入或读取失败，相关数量可能偏低：${sourceGaps.join('、')}`"
    />

    <div v-if="summary" class="ht-toolbar ht-block">
      <a-radio-group v-model:value="typeFilter" size="small" button-style="solid">
        <a-radio-button value="">全部</a-radio-button>
        <a-radio-button value="critical_value">危急值</a-radio-button>
        <a-radio-button value="unclosed_alert">未闭环告警</a-radio-button>
      </a-radio-group>
      <a-checkbox v-model:checked="hideConfirmed">隐藏已确认</a-checkbox>
    </div>

    <a-spin :spinning="detailLoading">
      <div v-if="visibleGroups.length" class="ht-groups">
        <section v-for="g in visibleGroups" :key="g.patient.patient_id" class="ht-group">
          <div class="ht-group__head">
            <span class="ht-bed">{{ g.patient.bed || '—' }}</span>
            <span class="ht-name">{{ g.patient.name }}</span>
            <a-tag :color="RISK_COLORS[g.patient.risk_level] || 'default'">{{ RISK_LABELS[g.patient.risk_level] || g.patient.risk_level }}</a-tag>
            <span class="ht-diag">{{ g.patient.diagnosis }}</span>
            <span class="ht-count">危急值 {{ g.patient.critical_value_count }} · 未闭环 {{ g.patient.unclosed_alert_count }}</span>
            <a-button size="small" type="link" @click="openIsbar(g.patient.patient_id)">去 ISBAR 交代</a-button>
          </div>
          <div v-if="g.error" class="ht-item ht-item--error">明细加载失败：{{ g.error }}（汇总计数仍有效）</div>
          <div v-else-if="!g.items.length" class="ht-item ht-muted">计数显示有未闭环项，但未查询到明细记录，请到患者告警页核对</div>
          <div
            v-for="item in g.items"
            :key="item.item_id || item.description"
            class="ht-item"
            :class="item.item_type === 'critical_value' ? 'ht-item--critical' : 'ht-item--warning'"
          >
            <span class="ht-type">{{ item.item_type === 'critical_value' ? '危急值' : '未闭环' }}</span>
            <span class="ht-desc">{{ item.description }}</span>
            <span v-if="item.confirmed" class="ht-confirmed">已确认 {{ item.confirmed_by }} {{ formatDateTime(item.confirmed_at) }}</span>
            <span v-else class="ht-pending">待交代</span>
          </div>
        </section>
      </div>
      <a-empty
        v-else-if="!loading && summary"
        :description="bedsWithItems.length ? '当前筛选条件下无待办项' : '本班无危急值和未闭环告警'"
      />
    </a-spin>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  Alert as AAlert, Button as AButton, Checkbox as ACheckbox, Empty as AEmpty, Radio as ARadio,
  Spin as ASpin, Tag as ATag,
} from 'ant-design-vue'
import { getForcedAlerts } from '../../api/handover'
import {
  useShiftSummary, formatDateTime, RISK_LABELS, RISK_COLORS, RISK_ORDER, type ShiftPatientStat,
} from '../../composables/useShiftSummary'

const ARadioGroup = ARadio.Group
const ARadioButton = ARadio.Button

interface ForcedItem {
  item_id: string
  item_type: string
  description: string
  confirmed: boolean
  confirmed_by: string
  confirmed_at: string
}
interface Group { patient: ShiftPatientStat; items: ForcedItem[]; error: string }

const router = useRouter()
const { loading, error, summary, patients, load } = useShiftSummary()
const detailLoading = ref(false)
const groups = ref<Group[]>([])
const typeFilter = ref('')
const hideConfirmed = ref(false)

const SOURCE_LABELS: Record<string, string> = {
  orders: '医嘱', tasks: '护理任务', alerts: '告警', devices: '设备', vitals: '生命体征', labs: '检验',
}
const sourceGaps = computed(() => {
  const s = summary.value || {}
  const list = [...(s.missing_sources || []), ...(s.failed_sources || [])]
  return Array.from(new Set(list.map((x: string) => SOURCE_LABELS[x] || x)))
})

function countOrNA(value: number, source: string) {
  const s = summary.value || {}
  const gaps = [...(s.missing_sources || []), ...(s.failed_sources || [])]
  return gaps.includes(source) ? '未接入' : (value ?? 0)
}

const bedsWithItems = computed(() =>
  patients.value
    .filter((p) => p.critical_value_count > 0 || p.unclosed_alert_count > 0)
    .sort((a, b) => (b.critical_value_count - a.critical_value_count)
      || ((RISK_ORDER[a.risk_level] ?? 9) - (RISK_ORDER[b.risk_level] ?? 9))
      || (b.unclosed_alert_count - a.unclosed_alert_count)),
)

const visibleGroups = computed(() =>
  groups.value
    .map((g) => ({
      ...g,
      items: g.items
        .filter((i) => !typeFilter.value || i.item_type === typeFilter.value)
        .filter((i) => !hideConfirmed.value || !i.confirmed),
    }))
    .filter((g) => g.error || g.items.length || (!typeFilter.value && !hideConfirmed.value)),
)

async function loadDetails() {
  const targets = bedsWithItems.value
  if (!targets.length) { groups.value = []; return }
  detailLoading.value = true
  const params = summary.value?.data_start && summary.value?.data_end
    ? { since: summary.value.data_start, until: summary.value.data_end }
    : undefined
  const result: Group[] = targets.map((p) => ({ patient: p, items: [], error: '' }))
  // 限制并发，避免一次性打满后端
  let cursor = 0
  async function worker() {
    while (cursor < result.length) {
      const g = result[cursor++]
      if (!g) break
      try {
        const res = await getForcedAlerts(g.patient.patient_id, params)
        g.items = (res.data?.forced_confirmations || []) as ForcedItem[]
        g.items.sort((a, b) => Number(b.item_type === 'critical_value') - Number(a.item_type === 'critical_value'))
      } catch (e: any) {
        const d = e?.response?.data?.detail
        g.error = (typeof d === 'object' ? d?.message : d) || e?.message || '请求失败'
      }
    }
  }
  try {
    await Promise.all(Array.from({ length: Math.min(4, result.length) }, worker))
    groups.value = result
  } finally {
    detailLoading.value = false
  }
}

async function reload() {
  await load()
  await loadDetails()
}

function openIsbar(patientId: string) {
  router.push({ name: 'handover-patient', params: { patientId } })
}

onMounted(reload)
</script>

<style scoped>
.handover-tasks { padding: var(--page-padding, 24px); max-width: 1400px; margin: 0 auto; width: 100%; }
.ht-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 16px; }
.ht-title { margin: 0; font-size: var(--text-page-title, 20px); font-weight: 600; color: var(--color-text-primary); }
.ht-subtitle { margin: 4px 0 0; font-size: var(--text-body, 13px); color: var(--color-text-secondary); }
.ht-block { margin-bottom: 12px; }
.ht-metrics { display: grid; grid-template-columns: repeat(6, 1fr); gap: 8px; }
.ht-metric { background: var(--color-bg-surface); border: 1px solid var(--color-border); border-radius: var(--radius-md, 6px); padding: 10px 12px; display: flex; flex-direction: column; }
.ht-metric b { font-size: 22px; color: var(--color-text-primary); }
.ht-metric span { font-size: var(--text-caption, 12px); color: var(--color-text-secondary); }
.ht-metric--critical b { color: var(--color-critical, #D92D20); }
.ht-metric--warning b { color: var(--color-warning, #B54708); }
.ht-toolbar { display: flex; align-items: center; gap: 12px; }
.ht-groups { display: flex; flex-direction: column; gap: 10px; }
.ht-group { background: var(--color-bg-surface); border: 1px solid var(--color-border); border-radius: var(--radius-lg, 10px); overflow: hidden; }
.ht-group__head { display: flex; align-items: center; gap: 10px; padding: 10px 14px; background: var(--color-bg-surface-secondary); border-bottom: 1px solid var(--color-border); }
.ht-bed { font-weight: 700; font-size: 15px; color: var(--color-text-primary); }
.ht-name { font-weight: 600; color: var(--color-text-primary); }
.ht-diag { font-size: var(--text-caption, 12px); color: var(--color-text-secondary); flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ht-count { font-size: var(--text-caption, 12px); color: var(--color-text-secondary); }
.ht-item { display: flex; align-items: center; gap: 10px; padding: 8px 14px; border-bottom: 1px solid var(--color-border); font-size: var(--text-body, 13px); }
.ht-item:last-child { border-bottom: none; }
.ht-item--critical { box-shadow: inset 3px 0 0 var(--color-critical, #D92D20); }
.ht-item--warning { box-shadow: inset 3px 0 0 var(--color-warning, #B54708); }
.ht-item--error { color: var(--color-critical, #D92D20); }
.ht-type { flex-shrink: 0; font-size: var(--text-caption, 12px); padding: 1px 6px; border-radius: var(--radius-tag, 4px); background: var(--color-bg-inset); color: var(--color-text-secondary); }
.ht-item--critical .ht-type { background: var(--color-critical-bg, #FEECEB); color: var(--color-critical, #D92D20); }
.ht-desc { flex: 1; min-width: 0; color: var(--color-text-primary); font-family: 'SF Mono', Consolas, monospace; font-size: var(--text-caption, 12px); }
.ht-confirmed { font-size: var(--text-caption, 12px); color: var(--color-normal, #12A66A); }
.ht-pending { font-size: var(--text-caption, 12px); color: var(--color-warning, #B54708); font-weight: 600; }
.ht-muted { color: var(--color-text-tertiary); font-size: var(--text-caption, 12px); }
@media (max-width: 1024px) { .ht-metrics { grid-template-columns: repeat(3, 1fr); } }
</style>
