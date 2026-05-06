<template>
  <section class="clinical-summary">
    <div class="summary-head">
      <div>
        <span>最近 {{ summary?.hours || 24 }} 小时临床摘要</span>
        <strong>{{ patientTitle }}</strong>
      </div>
      <button type="button" :disabled="loading" @click="$emit('refresh')">{{ loading ? '刷新中' : '刷新' }}</button>
    </div>
    <div v-if="loading" class="summary-empty">正在整理 24 小时事件、预警和待办...</div>
    <div v-else-if="!summary" class="summary-empty">暂无摘要数据，建议先确认监护、检验和预警同步状态。</div>
    <template v-else>
      <div class="summary-text">
        <span v-for="line in summaryLines" :key="line">{{ line }}</span>
      </div>
      <section class="top-problems">
        <div class="section-title">当前最危险的 3 件事</div>
        <article v-for="item in topProblems" :key="`${item.rank}-${item.problem}`" :class="['problem-card', `risk-${item.risk || 'unknown'}`]">
          <div class="problem-head">
            <b>{{ item.rank }}</b>
            <strong>{{ item.problem }}</strong>
            <em>{{ item.status || '待确认' }}</em>
          </div>
          <p>证据：{{ listText(item.evidence) }}</p>
          <p>建议：{{ listText(item.suggestions) }}</p>
          <div class="problem-foot">
            <span>风险：{{ riskText(item.risk) }}</span>
            <span>复评：{{ item.review_time ? fmt(item.review_time) : '建议 2 小时内复评关键指标' }}</span>
          </div>
        </article>
      </section>
      <section class="worsening">
        <div class="section-title">指标恶化趋势</div>
        <div v-if="(summary.worsening_indicators || []).length" class="worse-grid">
          <span v-for="item in summary.worsening_indicators" :key="`${item.name}-${item.time}`">
            {{ item.name || '指标' }} {{ arrow(item.direction) }} {{ item.from ?? '—' }} → {{ item.to ?? '—' }} {{ item.unit || '' }}
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

const props = defineProps<{ summary: any; loading?: boolean }>()
defineEmits<{ (e: 'refresh'): void }>()

const patientTitle = computed(() => {
  const p = props.summary?.patient || {}
  return `${p.bed || '--'}床 ${p.name || '未知患者'}`
})
const summaryLines = computed(() => String(props.summary?.summary || '').split('\n').filter(Boolean))
const topProblems = computed(() => (props.summary?.top_problems || []).slice(0, 3))

function listText(items: any[]) {
  const rows = Array.isArray(items) ? items.map((item) => String(item || '').trim()).filter(Boolean) : []
  return rows.length ? rows.slice(0, 3).join('；') : '暂无明确依据'
}
function riskText(value: string) {
  const map: Record<string, string> = { critical: '危急', high: '高风险', warning: '预警', info: '提示', unknown: '待确认' }
  return map[String(value || '').toLowerCase()] || value || '待确认'
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
  gap: 12px;
  padding: 14px;
  border-radius: 14px;
  border: 1px solid rgba(80, 199, 255, 0.14);
  background: linear-gradient(180deg, rgba(7, 20, 34, 0.9), rgba(4, 12, 22, 0.96));
}
.summary-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.summary-head div {
  display: grid;
  gap: 4px;
}
.summary-head span,
.section-title {
  color: #8cb7c9;
  font-size: 12px;
  font-weight: 700;
}
.summary-head strong {
  color: #ecfeff;
  font-size: 18px;
}
.summary-head button {
  border: 1px solid rgba(125, 211, 252, 0.2);
  background: rgba(8, 28, 44, 0.72);
  color: #dffbff;
  border-radius: 8px;
  padding: 6px 10px;
}
.summary-text {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 8px;
}
.summary-text span,
.worse-grid span,
.summary-empty,
.safety {
  padding: 9px 10px;
  border-radius: 10px;
  border: 1px solid rgba(125, 211, 252, 0.12);
  background: rgba(8, 28, 44, 0.58);
  color: #dffbff;
  font-size: 12px;
}
.top-problems {
  display: grid;
  gap: 10px;
}
.problem-card {
  display: grid;
  gap: 7px;
  padding: 10px;
  border-radius: 12px;
  border: 1px solid rgba(125, 211, 252, 0.14);
  background: rgba(8, 28, 44, 0.72);
}
.problem-card p {
  margin: 0;
  color: #b9d6e4;
  font-size: 12px;
  line-height: 1.6;
}
.problem-head,
.problem-foot {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.problem-head b {
  display: grid;
  place-items: center;
  width: 24px;
  height: 24px;
  border-radius: 999px;
  background: rgba(59, 130, 246, 0.22);
  color: #fff;
}
.problem-head strong {
  color: #fff;
}
.problem-head em,
.problem-foot span {
  color: #9cc2d1;
  font-size: 11px;
  font-style: normal;
}
.risk-critical,
.risk-high {
  border-color: rgba(248, 113, 113, 0.26);
}
.risk-warning {
  border-color: rgba(245, 158, 11, 0.24);
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
.summary-empty.small {
  padding: 8px;
}
.safety {
  color: #fde68a;
}
html[data-theme='light'] .clinical-summary,
html[data-theme='light'] .summary-text span,
html[data-theme='light'] .worse-grid span,
html[data-theme='light'] .summary-empty,
html[data-theme='light'] .problem-card,
html[data-theme='light'] .safety {
  border-color: rgba(187, 204, 220, 0.72);
  background: #fff;
}
html[data-theme='light'] .summary-head strong,
html[data-theme='light'] .problem-head strong {
  color: #16324f;
}
html[data-theme='light'] .summary-text span,
html[data-theme='light'] .worse-grid span,
html[data-theme='light'] .problem-card p,
html[data-theme='light'] .summary-empty {
  color: #334155;
}
html[data-theme='light'] .safety {
  color: #92400e;
  background: #fffbeb;
}
</style>
