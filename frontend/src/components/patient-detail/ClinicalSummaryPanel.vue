<template>
  <section class="clinical-summary">
    <div class="summary-head">
      <div class="title-block">
        <span class="eyebrow">临床摘要</span>
        <strong>{{ patientTitle }}</strong>
        <small>最近 {{ summary?.hours || 24 }} 小时临床摘要</small>
      </div>
      <button type="button" class="refresh-btn" :disabled="loading" @click="$emit('refresh')">{{ loading ? '刷新中' : '刷新' }}</button>
    </div>
    <div v-if="loading" class="summary-empty">正在整理 24 小时事件、预警和待办...</div>
    <div v-else-if="!summary" class="summary-empty">暂无摘要数据，建议先确认监护、检验和预警同步状态。</div>
    <template v-else>
      <div class="summary-metrics">
        <article v-for="line in summaryCards" :key="`${line.label}-${line.value}`" class="metric-item">
          <span>{{ line.label }}</span>
          <strong>{{ line.value }}</strong>
        </article>
      </div>
      <section class="top-problems">
        <div class="section-bar">
          <strong>当前最危险的 3 件事</strong>
          <span>问题 / 证据 / 建议 / 复评</span>
        </div>
        <div class="problem-grid">
        <article v-for="item in topProblems" :key="`${item.rank}-${item.problem}`" :class="['problem-card', `risk-${problemTone(item.risk)}`]">
          <div class="problem-head">
            <b>{{ item.rank }}</b>
            <div>
              <strong>{{ clinicalText(item.problem, '待确认问题') }}</strong>
              <em>{{ riskText(item.risk) }} · {{ statusText(item.status) }}</em>
            </div>
          </div>
          <dl>
            <dt>证据</dt>
            <dd>{{ listText(item.evidence) }}</dd>
            <dt>建议</dt>
            <dd>{{ listText(item.suggestions) }}</dd>
          </dl>
          <div class="problem-foot">
            <span>复评：{{ item.review_time ? fmt(item.review_time) : '建议 2 小时内复评关键指标' }}</span>
          </div>
        </article>
        </div>
      </section>
      <section class="worsening">
        <div class="section-bar compact">
          <strong>指标恶化趋势</strong>
          <span>最近 6-24 小时</span>
        </div>
        <div v-if="(summary.worsening_indicators || []).length" class="worse-grid">
          <span v-for="item in summary.worsening_indicators" :key="`${item.name}-${item.time}`">
            {{ clinicalTerm(item.name, '指标') }} {{ arrow(item.direction) }} {{ clinicalText(item.from, '—') }} → {{ clinicalText(item.to, '—') }} {{ clinicalText(item.unit, '') }}
          </span>
        </div>
        <div v-else class="summary-empty small">近窗口未提取到明确恶化指标，可能因数据缺失或暂无趋势型预警。</div>
      </section>
      <div class="safety">{{ summary.safety_notice || '以上为临床辅助信息，不替代医生判断。' }}</div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import dayjs from 'dayjs'
import { formatClinicalTermLabel, formatClinicalText, formatRiskLevelLabel, formatStatusLabel } from '../../utils/displayLabels'

const props = defineProps<{ summary: any; loading?: boolean }>()
defineEmits<{ (e: 'refresh'): void }>()

const patientTitle = computed(() => {
  const p = props.summary?.patient || {}
  return `${p.bed || '--'}床 ${p.name || '未知患者'}`
})
const summaryLines = computed(() => String(props.summary?.summary || '').split('\n').filter(Boolean))
const summaryCards = computed(() =>
  summaryLines.value.map((line) => {
    const parts = String(line).split(/[:：]/)
    const label = parts.shift()?.trim() || '摘要'
    const value = parts.join('：').trim() || line
    return {
      label: formatClinicalText(label, '摘要'),
      value: formatClinicalText(value, '暂无'),
    }
  }),
)
const topProblems = computed(() => (props.summary?.top_problems || []).slice(0, 3))

function listText(items: any[]) {
  const rows = Array.isArray(items) ? items.map((item) => formatClinicalText(item, '').trim()).filter(Boolean) : []
  return rows.length ? rows.slice(0, 3).join('；') : '暂无明确依据'
}
function riskText(value: string) {
  return formatRiskLevelLabel(value, '待确认')
}
function statusText(value: any) {
  return formatStatusLabel(value, '待确认')
}
function clinicalTerm(value: any, fallback = '临床指标') {
  return formatClinicalTermLabel(value, fallback)
}
function clinicalText(value: any, fallback = '暂无') {
  return formatClinicalText(value, fallback)
}
function problemTone(value: string) {
  const key = String(value || '').toLowerCase()
  if (key === 'critical' || key === 'high') return 'critical'
  if (key === 'warning') return 'warning'
  if (key === 'info') return 'info'
  return 'unknown'
}
function arrow(value: string) {
  if (value === 'up') return '↑'
  if (value === 'down') return '↓'
  return '↔'
}
function fmt(value: any) {
  return value ? dayjs(value).format('MM-DD HH:mm') : '—'
}
</script>

<style scoped>
.clinical-summary {
  display: grid;
  gap: 14px;
  padding: 14px;
  border-radius: 10px;
  border: 1px solid rgba(125, 211, 252, 0.16);
  background: rgba(5, 16, 28, 0.78);
  box-shadow: inset 0 1px 0 var(--border-color);
}
.summary-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-width: 0;
}
.title-block {
  display: grid;
  gap: 3px;
  min-width: 0;
}
.eyebrow,
.title-block small,
.section-bar span {
  color: #8fb2c5;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0;
}
.summary-head strong {
  color: #ecfeff;
  font-size: 17px;
  line-height: 1.25;
}
.refresh-btn {
  flex: 0 0 auto;
  border: 1px solid rgba(125, 211, 252, 0.2);
  background: rgba(14, 45, 68, 0.72);
  color: #dffbff;
  border-radius: 8px;
  padding: 6px 12px;
  font-size: 12px;
  cursor: pointer;
}
.refresh-btn:disabled {
  cursor: not-allowed;
  opacity: 0.7;
}
.summary-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}
.metric-item {
  min-height: 64px;
  padding: 10px;
  border-radius: 8px;
  border: 1px solid rgba(125, 211, 252, 0.12);
  background: rgba(10, 31, 48, 0.62);
}
.metric-item span {
  display: block;
  margin-bottom: 6px;
  color: #91b7c8;
  font-size: 11px;
}
.metric-item strong {
  color: #dffbff;
  font-size: 12px;
  font-weight: 700;
  line-height: 1.45;
}
.top-problems {
  display: grid;
  gap: 10px;
}
.section-bar {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  padding-top: 2px;
}
.section-bar strong {
  color: #e8fbff;
  font-size: 14px;
}
.section-bar.compact {
  margin-top: 2px;
}
.problem-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}
.problem-card {
  display: grid;
  align-content: start;
  gap: 10px;
  min-height: 178px;
  padding: 10px 10px 10px 12px;
  border-radius: 8px;
  border: 1px solid rgba(125, 211, 252, 0.14);
  border-left: 3px solid rgba(148, 163, 184, 0.7);
  background: rgba(9, 29, 45, 0.68);
}
.problem-head {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  min-width: 0;
}
.problem-head b {
  flex: 0 0 auto;
  display: grid;
  place-items: center;
  width: 22px;
  height: 22px;
  border-radius: 6px;
  background: rgba(59, 130, 246, 0.2);
  color: #fff;
  font-size: 12px;
}
.problem-head strong {
  display: block;
  color: #fff;
  font-size: 13px;
  line-height: 1.35;
}
.problem-head em,
.problem-foot span,
.worse-grid span,
.summary-empty,
.safety {
  color: #9cc2d1;
  font-size: 11px;
  font-style: normal;
}
.problem-card dl {
  display: grid;
  gap: 5px 8px;
  grid-template-columns: 34px minmax(0, 1fr);
  margin: 0;
}
.problem-card dt,
.problem-card dd {
  margin: 0;
  font-size: 12px;
  line-height: 1.55;
}
.problem-card dt {
  color: #7fa6b8;
  font-weight: 700;
}
.problem-card dd {
  color: #c7dde8;
}
.problem-foot {
  padding-top: 8px;
  border-top: 1px solid rgba(125, 211, 252, 0.1);
}
.risk-critical,
.risk-high {
  border-left-color: #f87171;
  background: rgba(53, 18, 26, 0.26);
}
.risk-warning {
  border-left-color: #f59e0b;
  background: rgba(54, 34, 10, 0.26);
}
.risk-info {
  border-left-color: #38bdf8;
}
.worsening {
  display: grid;
  gap: 8px;
}
.worse-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.worse-grid span,
.summary-empty,
.safety {
  padding: 8px 10px;
  border-radius: 8px;
  border: 1px solid rgba(125, 211, 252, 0.12);
  background: rgba(10, 31, 48, 0.58);
}
.summary-empty.small {
  padding: 8px;
}
.safety {
  border-color: rgba(245, 158, 11, 0.22);
  background: rgba(68, 45, 12, 0.42);
  color: #fde68a;
}
html[data-theme='light'] .clinical-summary,
html[data-theme='light'] .metric-item,
html[data-theme='light'] .worse-grid span,
html[data-theme='light'] .summary-empty,
html[data-theme='light'] .problem-card,
html[data-theme='light'] .safety {
  border-color: rgba(187, 204, 220, 0.72);
  background: #fff;
}
html[data-theme='light'] .summary-head strong,
html[data-theme='light'] .problem-head strong,
html[data-theme='light'] .section-bar strong {
  color: #16324f;
}
html[data-theme='light'] .metric-item strong,
html[data-theme='light'] .worse-grid span,
html[data-theme='light'] .problem-card dd,
html[data-theme='light'] .summary-empty {
  color: #334155;
}
html[data-theme='light'] .metric-item span,
html[data-theme='light'] .problem-card dt,
html[data-theme='light'] .title-block small,
html[data-theme='light'] .eyebrow,
html[data-theme='light'] .section-bar span {
  color: #64748b;
}
html[data-theme='light'] .safety {
  color: #92400e;
  background: #fffbeb;
}

/* === Additional light-mode overrides === */
html[data-theme='light'] .metric-item {
  background: rgba(243,248,252,0.96);
  border-color: rgba(187,204,220,0.72);
}
html[data-theme='light'] .metric-item span { color: #47627e; }
html[data-theme='light'] .metric-item strong { color: #0f172a; }
html[data-theme='light'] .refresh-btn {
  background: rgba(241,246,251,0.98);
  border-color: rgba(187,204,220,0.72);
  color: #1d4ed8;
}
html[data-theme='light'] .risk-critical,
html[data-theme='light'] .risk-high {
  background: rgba(254,226,226,0.6);
  color: #991b1b;
}
html[data-theme='light'] .risk-warning {
  background: rgba(254,243,199,0.6);
  color: #92400e;
}
html[data-theme='light'] .worse-grid span,
html[data-theme='light'] .summary-empty {
  background: rgba(243,248,252,0.96);
  border-color: rgba(187,204,220,0.72);
}

@media (max-width: 1180px) {
  .summary-metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .problem-grid {
    grid-template-columns: 1fr;
  }
  .problem-card {
    min-height: 0;
  }
}
@media (max-width: 640px) {
  .summary-head,
  .section-bar {
    align-items: flex-start;
    flex-direction: column;
  }
  .summary-metrics {
    grid-template-columns: 1fr;
  }
}
</style>
