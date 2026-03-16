<template>
  <section class="sbt-wrap">
    <header class="sbt-head">
      <div>
        <div class="sbt-title">SBT Timeline / Record</div>
        <div class="sbt-sub">自主呼吸试验结构化时间线，聚焦结果、参数与失败线索</div>
      </div>
      <button type="button" class="sbt-refresh" @click="onRefresh">
        {{ loading ? '刷新中…' : '刷新记录' }}
      </button>
    </header>

    <section v-if="summaryCards.length" class="sbt-kpi-strip">
      <article v-for="card in summaryCards" :key="card.label" class="sbt-kpi-card">
        <span>{{ card.label }}</span>
        <strong>{{ card.value }}</strong>
        <small>{{ card.meta }}</small>
      </article>
    </section>

    <div v-if="loading && !records.length" class="sbt-empty">正在加载 SBT 记录…</div>
    <div v-else-if="error && !records.length" class="sbt-empty sbt-empty--error">{{ error }}</div>
    <div v-else-if="!records.length" class="sbt-empty">暂无 SBT 结构化记录</div>

    <div v-else class="sbt-content">
      <section class="sbt-timeline">
        <article
          v-for="(row, idx) in records"
          :key="`${row.trial_time || row.created_at || idx}`"
          :class="['sbt-timeline-item', `sbt-${resultTone(row.result)}`]"
        >
          <div class="sbt-time-rail">
            <span class="sbt-time">{{ fmtTime(row.trial_time || row.created_at) || '时间未知' }}</span>
            <i :class="['sbt-dot', `sbt-dot--${resultTone(row.result)}`]" />
            <span v-if="idx < records.length - 1" class="sbt-line" />
          </div>
          <div class="sbt-card">
            <div class="sbt-card-head">
              <div>
                <div class="sbt-card-title-row">
                  <strong class="sbt-card-title">{{ row.label || 'SBT记录' }}</strong>
                  <span :class="['sbt-result-pill', `sbt-result-pill--${resultTone(row.result)}`]">{{ row.label || '已记录SBT' }}</span>
                </div>
                <div class="sbt-card-sub">
                  来源 {{ row.source || '—' }}
                  <span v-if="row.duration_minutes != null"> · 时长 {{ row.duration_minutes }} min</span>
                  <span v-if="row.source_code"> · {{ row.source_code }}</span>
                </div>
              </div>
              <div class="sbt-score-box">
                <span>RSBI</span>
                <strong>{{ valueOrDash(row.rsbi) }}</strong>
              </div>
            </div>

            <div class="sbt-chip-row">
              <span class="sbt-chip">RR {{ valueOrDash(row.rr) }}</span>
              <span class="sbt-chip">Vte {{ valueOrDash(row.vte_ml) }}</span>
              <span class="sbt-chip">FiO₂ {{ valueOrDash(row.fio2) }}</span>
              <span class="sbt-chip">PEEP {{ valueOrDash(row.peep) }}</span>
              <span v-if="row.minute_vent != null" class="sbt-chip">MV {{ valueOrDash(row.minute_vent) }}</span>
            </div>

            <div class="sbt-record-grid">
              <div class="sbt-record-item">
                <span class="sbt-record-label">结果</span>
                <span class="sbt-record-value">{{ row.label || '—' }}</span>
              </div>
              <div class="sbt-record-item">
                <span class="sbt-record-label">是否通过</span>
                <span class="sbt-record-value">{{ row.passed == null ? '—' : row.passed ? '是' : '否' }}</span>
              </div>
              <div class="sbt-record-item">
                <span class="sbt-record-label">试验时间</span>
                <span class="sbt-record-value">{{ fmtTime(row.trial_time || row.created_at) || '—' }}</span>
              </div>
              <div class="sbt-record-item">
                <span class="sbt-record-label">原始文本</span>
                <span class="sbt-record-value">{{ row.raw_text || '—' }}</span>
              </div>
            </div>
          </div>
        </article>
      </section>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  summary: any
  records: any[]
  loading: boolean
  error: string
  onRefresh: () => void
  fmtTime: (value: any) => string
}>()

const summaryCards = computed(() => {
  const summary = props.summary && typeof props.summary === 'object' ? props.summary : {}
  return [
    { label: '记录总数', value: summary.total_records ?? 0, meta: 'SBT records' },
    { label: '通过', value: summary.passed_count ?? 0, meta: 'passed' },
    { label: '失败', value: summary.failed_count ?? 0, meta: 'failed' },
    { label: '最近一次', value: props.fmtTime(summary.last_trial_time) || '—', meta: 'last trial' },
  ]
})

function resultTone(raw: any) {
  const value = String(raw || '').toLowerCase()
  if (value === 'passed') return 'passed'
  if (value === 'failed') return 'failed'
  return 'documented'
}

function valueOrDash(value: any) {
  if (value == null || value === '') return '—'
  const num = Number(value)
  if (Number.isNaN(num)) return String(value)
  return Number.isInteger(num) ? String(num) : num.toFixed(1)
}
</script>

<style scoped>
.sbt-wrap { display: grid; gap: 12px; }
.sbt-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.sbt-title {
  color: #ecfeff;
  font-size: 18px;
  font-weight: 800;
  letter-spacing: .04em;
}
.sbt-sub {
  margin-top: 4px;
  color: #88b6c8;
  font-size: 12px;
}
.sbt-refresh {
  min-height: 34px;
  padding: 0 14px;
  border-radius: 10px;
  border: 1px solid rgba(80,199,255,.16);
  background: linear-gradient(180deg, rgba(9,46,70,.96) 0%, rgba(6,27,42,.98) 100%);
  color: #dffbff;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
}
.sbt-kpi-strip {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}
.sbt-kpi-card,
.sbt-card {
  border-radius: 14px;
  border: 1px solid rgba(80,199,255,.12);
  background:
    radial-gradient(circle at top right, rgba(34,211,238,.06), rgba(34,211,238,0) 30%),
    linear-gradient(180deg, rgba(7,20,34,.96) 0%, rgba(4,12,22,.98) 100%);
  box-shadow: inset 0 1px 0 rgba(145,228,255,.04), 0 12px 24px rgba(0,0,0,.18);
}
.sbt-kpi-card {
  padding: 12px 14px;
  display: grid;
  gap: 6px;
}
.sbt-kpi-card > span {
  color: #74dff3;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: .14em;
  text-transform: uppercase;
}
.sbt-kpi-card > strong {
  color: #effcff;
  font-size: 26px;
  line-height: 1;
  font-family: 'Rajdhani', 'SF Mono', 'Consolas', monospace;
}
.sbt-kpi-card > small {
  color: #86adc0;
  font-size: 11px;
}
.sbt-empty {
  padding: 24px 16px;
  border-radius: 14px;
  border: 1px solid rgba(80,199,255,.12);
  background: rgba(7,20,34,.92);
  color: #9bcde0;
  font-size: 13px;
  text-align: center;
}
.sbt-empty--error {
  color: #fda4af;
  border-color: rgba(251,113,133,.18);
}
.sbt-content { display: grid; gap: 12px; }
.sbt-timeline { display: grid; gap: 12px; }
.sbt-timeline-item {
  display: grid;
  grid-template-columns: 100px 1fr;
  gap: 12px;
}
.sbt-time-rail {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding-top: 6px;
}
.sbt-time {
  color: #73cde0;
  font-size: 11px;
  writing-mode: vertical-rl;
  transform: rotate(180deg);
}
.sbt-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
}
.sbt-dot--passed { background: #22c55e; box-shadow: 0 0 8px rgba(34,197,94,.55); }
.sbt-dot--failed { background: #fb5a7a; box-shadow: 0 0 8px rgba(251,90,122,.55); }
.sbt-dot--documented { background: #38bdf8; box-shadow: 0 0 8px rgba(56,189,248,.45); }
.sbt-line {
  width: 2px;
  flex: 1 1 auto;
  border-radius: 999px;
  background: linear-gradient(180deg, #1f3c67 0%, #0f233f 100%);
}
.sbt-card { padding: 14px; display: grid; gap: 10px; }
.sbt-passed .sbt-card { border-color: rgba(34,197,94,.2); }
.sbt-failed .sbt-card { border-color: rgba(251,90,122,.2); }
.sbt-card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}
.sbt-card-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.sbt-card-title {
  color: #effcff;
  font-size: 15px;
}
.sbt-card-sub {
  margin-top: 4px;
  color: #8fb8ca;
  font-size: 12px;
}
.sbt-result-pill {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 0 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  border: 1px solid transparent;
}
.sbt-result-pill--passed { color: #6ee7b7; background: #10372b; border-color: #14532d; }
.sbt-result-pill--failed { color: #fda4af; background: #47131d; border-color: #7f1d32; }
.sbt-result-pill--documented { color: #93dcff; background: rgba(10,40,62,.9); border-color: rgba(56,189,248,.22); }
.sbt-score-box {
  min-width: 88px;
  padding: 8px 10px;
  border-radius: 10px;
  border: 1px solid rgba(80,199,255,.14);
  background: rgba(8,31,49,.86);
  text-align: right;
}
.sbt-score-box span {
  display: block;
  color: #8fe6f4;
  font-size: 11px;
}
.sbt-score-box strong {
  display: block;
  color: #effcff;
  font-size: 24px;
  line-height: 1;
  font-family: 'Rajdhani', 'SF Mono', 'Consolas', monospace;
}
.sbt-chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.sbt-chip {
  display: inline-flex;
  align-items: center;
  min-height: 30px;
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px solid rgba(79,182,219,.18);
  background: rgba(8,28,44,.82);
  color: #dffbff;
  font-size: 12px;
}
.sbt-record-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px 10px;
}
.sbt-record-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  font-size: 11px;
  color: #9ca3af;
  background: #0f2038;
  border: 1px solid #1c3d64;
  border-radius: 8px;
  padding: 6px 8px;
}
.sbt-record-label { color: #7aa2d6; }
.sbt-record-value {
  color: #e5e7eb;
  font-weight: 600;
  text-align: right;
  max-width: 68%;
  word-break: break-word;
}
@media (max-width: 980px) {
  .sbt-kpi-strip { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .sbt-timeline-item { grid-template-columns: 1fr; }
  .sbt-time-rail {
    flex-direction: row;
    justify-content: flex-start;
    align-items: center;
  }
  .sbt-time {
    writing-mode: initial;
    transform: none;
  }
  .sbt-line { display: none; }
}
@media (max-width: 640px) {
  .sbt-kpi-strip,
  .sbt-record-grid { grid-template-columns: 1fr; }
  .sbt-card-head { flex-direction: column; }
  .sbt-score-box {
    width: 100%;
    text-align: left;
  }
}
</style>
