<template>
  <section class="similar-wrap">
    <header class="similar-head">
      <div>
        <div class="similar-title">相似病例结局回溯</div>
        <div class="similar-sub">按诊断 / 入科 SOFA / 呼吸机 / CRRT 维度匹配历史出科患者</div>
      </div>
      <button type="button" class="similar-refresh" @click="onRefresh">
        {{ loading ? '刷新中…' : '刷新匹配' }}
      </button>
    </header>

    <div v-if="currentProfileChips.length" class="profile-strip">
      <span v-for="chip in currentProfileChips" :key="chip.label" class="profile-chip">
        <i class="profile-chip-dot" />
        {{ chip.label }} {{ chip.value }}
      </span>
    </div>

    <div v-if="loading && !hasReview" class="similar-empty">正在检索相似病例…</div>
    <div v-else-if="error && !hasReview" class="similar-empty similar-empty--warn">{{ error }}</div>
    <div v-else-if="!cases.length" class="similar-empty">暂无可展示的相似出院病例</div>

    <template v-else>
      <div v-if="softNotice" class="similar-soft-notice">{{ softNotice }}</div>
      <section class="kpi-strip">
        <article class="kpi-card">
          <span>匹配病例</span>
          <strong>{{ summary.matched_cases ?? 0 }}</strong>
          <small>展示 {{ summary.displayed_cases ?? cases.length }}</small>
        </article>
        <article class="kpi-card">
          <span>存活率</span>
          <strong>{{ percentText(summary.survival_rate) }}</strong>
          <small>历史事实回溯</small>
        </article>
        <article class="kpi-card">
          <span>平均 ICU 天数</span>
          <strong>{{ valueOrDash(summary.avg_icu_days) }}</strong>
          <small>days</small>
        </article>
        <article class="kpi-card">
          <span>平均机械通气天数</span>
          <strong>{{ valueOrDash(summary.avg_vent_days) }}</strong>
          <small>days</small>
        </article>
      </section>

      <section class="outcome-board">
        <div class="section-head">
          <span class="section-title">结局统计条</span>
          <span class="section-desc">Similar Outcome Distribution</span>
        </div>
        <div class="outcome-strip">
          <div
            v-for="item in outcomeItems"
            :key="item.key"
            :class="['outcome-seg', `outcome-seg--${item.tone}`]"
            :style="{ flex: Math.max(Number(item.count || 0), 0.35) }"
          >
            <span class="outcome-seg-label">{{ item.label }}</span>
            <strong class="outcome-seg-value">{{ item.count }}</strong>
          </div>
        </div>
      </section>

      <section class="case-list">
        <article v-for="(row, idx) in cases" :key="row.patient_id || idx" class="case-card">
          <div class="case-card-head">
            <div class="case-card-title-group">
              <div class="case-rank">CASE {{ String(Number(idx) + 1).padStart(2, '0') }}</div>
              <div class="case-title-row">
                <strong class="case-name">{{ row.patient_name || '历史病例' }}</strong>
                <span :class="['case-outcome-pill', `tone-${outcomeTone(row.outcome)}`]">{{ row.outcome || '已出院' }}</span>
              </div>
              <div class="case-meta-row">
                <span class="case-meta-pill" v-if="row.bed">床位 {{ row.bed }}</span>
                <span class="case-meta-pill">年龄 {{ valueOrDash(row.age_years) }}</span>
                <span class="case-meta-pill">入科 SOFA {{ valueOrDash(row.initial_sofa) }}</span>
                <span class="case-meta-pill">ICU {{ valueOrDash(row.icu_days) }} d</span>
                <span class="case-meta-pill">MV {{ valueOrDash(row.vent_days) }} d</span>
                <span v-if="row.crrt_used" class="case-meta-pill">CRRT</span>
              </div>
            </div>
            <div class="score-box">
              <span class="score-label">SIMILARITY</span>
              <strong class="score-value">{{ scorePercent(row.similarity_score) }}</strong>
              <small class="score-sub">诊断 {{ scorePercent(row.diag_similarity) }}</small>
            </div>
          </div>

          <div v-if="row.diagnosis_excerpt" class="case-diagnosis">{{ row.diagnosis_excerpt }}</div>

          <div v-if="Array.isArray(row.matched_dimensions) && row.matched_dimensions.length" class="match-chip-row">
            <span v-for="(item, itemIdx) in row.matched_dimensions" :key="`${row.patient_id || idx}-${itemIdx}`" class="match-chip">
              {{ item }}
            </span>
          </div>

          <div class="case-foot">
            <span>入科 {{ fmtTime(row.admission_time) || '—' }}</span>
            <span>出科 {{ fmtTime(row.discharge_time) || '—' }}</span>
          </div>
        </article>
      </section>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  review: any
  loading: boolean
  error: string
  onRefresh: () => void
  fmtTime: (value: any) => string
}>()

const summary = computed(() => (props.review?.summary && typeof props.review.summary === 'object' ? props.review.summary : {}))
const cases = computed(() => (Array.isArray(props.review?.cases) ? props.review.cases : []))
const hasReview = computed(() => !!props.review)
const softNotice = computed(() => {
  const fallbackMessage = String(summary.value?.fallback_message || '').trim()
  if (fallbackMessage) return fallbackMessage
  if (summary.value?.degraded && props.error) return props.error
  return ''
})

const outcomeItems = computed(() => {
  const outcomes = summary.value?.outcomes && typeof summary.value.outcomes === 'object' ? summary.value.outcomes : {}
  return [
    { key: 'improved', label: '好转出科', count: Number(outcomes['好转出科'] || 0), tone: 'green' },
    { key: 'home', label: '自动出院', count: Number(outcomes['自动出院'] || 0), tone: 'yellow' },
    { key: 'death', label: '死亡', count: Number(outcomes['死亡'] || 0), tone: 'red' },
    { key: 'discharged', label: '已出院', count: Number(outcomes['已出院'] || 0), tone: 'blue' },
  ]
})

const currentProfileChips = computed(() => {
  const current = props.review?.current_profile && typeof props.review.current_profile === 'object'
    ? props.review.current_profile
    : {}
  const rows: Array<{ label: string; value: string }> = []
  if (current.age_years != null) rows.push({ label: '年龄', value: String(current.age_years) })
  if (current.initial_sofa != null) rows.push({ label: '入科SOFA', value: String(current.initial_sofa) })
  rows.push({ label: '机械通气', value: current.vent_used ? '已使用' : '未使用' })
  rows.push({ label: 'CRRT', value: current.crrt_used ? '已使用' : '未使用' })
  if (Array.isArray(current.diagnosis_tokens) && current.diagnosis_tokens.length) {
    rows.push({ label: '诊断关键词', value: current.diagnosis_tokens.slice(0, 4).join(' / ') })
  }
  return rows
})

function percentText(value: any) {
  if (value == null || value === '') return '—'
  const num = Number(value)
  if (Number.isNaN(num)) return '—'
  return `${Math.round(num * 100)}%`
}

function scorePercent(value: any) {
  if (value == null || value === '') return '—'
  const num = Number(value)
  if (Number.isNaN(num)) return '—'
  return `${Math.round(num * 100)}%`
}

function valueOrDash(value: any) {
  if (value == null || value === '') return '—'
  const num = Number(value)
  if (Number.isNaN(num)) return String(value)
  return Number.isInteger(num) ? String(num) : num.toFixed(1)
}

function outcomeTone(raw: any) {
  const value = String(raw || '')
  if (value.includes('死亡')) return 'red'
  if (value.includes('自动')) return 'yellow'
  if (value.includes('好转')) return 'green'
  return 'blue'
}
</script>

<style scoped>
.similar-wrap {
  display: grid;
  gap: 12px;
}

.similar-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.similar-title {
  color: #ecfeff;
  font-size: 18px;
  font-weight: 800;
  letter-spacing: 0.04em;
}

.similar-sub {
  margin-top: 4px;
  color: #88b6c8;
  font-size: 12px;
}

.similar-refresh {
  min-height: 34px;
  padding: 0 14px;
  border-radius: 10px;
  border: 1px solid rgba(80, 199, 255, 0.16);
  background: linear-gradient(180deg, rgba(9, 46, 70, 0.96) 0%, rgba(6, 27, 42, 0.98) 100%);
  color: #dffbff;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.2s ease;
}

.similar-refresh:hover {
  border-color: rgba(103, 232, 249, 0.34);
  box-shadow: 0 0 16px rgba(34, 211, 238, 0.12);
}

.profile-strip,
.match-chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.profile-chip,
.match-chip,
.case-meta-pill {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px solid rgba(80, 199, 255, 0.12);
  background: rgba(8, 28, 44, 0.82);
  color: #dffbff;
  font-size: 12px;
}

.profile-chip {
  gap: 8px;
  background: rgba(7, 33, 50, 0.82);
}

.profile-chip-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #67e8f9;
  box-shadow: 0 0 10px rgba(103, 232, 249, 0.4);
}

.kpi-strip {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.kpi-card,
.outcome-board,
.case-card {
  border-radius: 14px;
  border: 1px solid rgba(80, 199, 255, 0.12);
  background:
    radial-gradient(circle at top right, rgba(34, 211, 238, 0.06), rgba(34, 211, 238, 0) 30%),
    linear-gradient(180deg, rgba(7, 20, 34, 0.96) 0%, rgba(4, 12, 22, 0.98) 100%);
  box-shadow: inset 0 1px 0 rgba(145, 228, 255, 0.04), 0 12px 24px rgba(0, 0, 0, 0.18);
}

.kpi-card {
  padding: 12px 14px;
  display: grid;
  gap: 6px;
}

.kpi-card > span,
.section-title {
  color: #74dff3;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.kpi-card > strong {
  color: #effcff;
  font-size: 28px;
  line-height: 1;
  font-family: 'Rajdhani', 'SF Mono', 'Consolas', monospace;
}

.kpi-card > small,
.section-desc {
  color: #86adc0;
  font-size: 11px;
}

.outcome-board {
  padding: 12px 14px 14px;
  display: grid;
  gap: 10px;
}

.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.outcome-strip {
  display: flex;
  gap: 8px;
  min-height: 76px;
}

.outcome-seg {
  min-width: 0;
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid rgba(80, 199, 255, 0.12);
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 6px;
}

.outcome-seg--green {
  background: linear-gradient(180deg, rgba(7, 63, 55, 0.88) 0%, rgba(7, 38, 34, 0.94) 100%);
  color: #7cf1d3;
}

.outcome-seg--yellow {
  background: linear-gradient(180deg, rgba(76, 55, 12, 0.88) 0%, rgba(44, 31, 8, 0.94) 100%);
  color: #fcd34d;
}

.outcome-seg--red {
  background: linear-gradient(180deg, rgba(72, 17, 31, 0.9) 0%, rgba(42, 10, 19, 0.94) 100%);
  color: #fda4af;
}

.outcome-seg--blue {
  background: linear-gradient(180deg, rgba(10, 40, 62, 0.88) 0%, rgba(7, 24, 38, 0.94) 100%);
  color: #93dcff;
}

.outcome-seg-label {
  font-size: 11px;
  font-weight: 700;
}

.outcome-seg-value {
  font-size: 26px;
  line-height: 1;
  font-family: 'Rajdhani', 'SF Mono', 'Consolas', monospace;
}

.case-list {
  display: grid;
  gap: 12px;
}

.case-card {
  padding: 14px;
  display: grid;
  gap: 10px;
}

.case-card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
}

.case-card-title-group {
  min-width: 0;
  display: grid;
  gap: 8px;
}

.case-rank {
  color: #61dff2;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.16em;
}

.case-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.case-name {
  color: #effcff;
  font-size: 16px;
  line-height: 1.2;
}

.case-outcome-pill {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 0 10px;
  border-radius: 999px;
  border: 1px solid transparent;
  font-size: 11px;
  font-weight: 700;
}

.case-outcome-pill.tone-green { color: #6ee7b7; background: rgba(7, 63, 55, 0.9); border-color: rgba(45, 212, 191, 0.22); }
.case-outcome-pill.tone-yellow { color: #fcd34d; background: rgba(76, 55, 12, 0.9); border-color: rgba(251, 191, 36, 0.22); }
.case-outcome-pill.tone-red { color: #fda4af; background: rgba(72, 17, 31, 0.9); border-color: rgba(251, 113, 133, 0.22); }
.case-outcome-pill.tone-blue { color: #93dcff; background: rgba(10, 40, 62, 0.9); border-color: rgba(56, 189, 248, 0.22); }

.case-meta-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.score-box {
  min-width: 110px;
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid rgba(80, 199, 255, 0.12);
  background: rgba(8, 29, 44, 0.9);
  text-align: right;
}

.score-label {
  display: block;
  color: #74dff3;
  font-size: 10px;
  letter-spacing: 0.12em;
}

.score-value {
  display: block;
  color: #effcff;
  font-size: 30px;
  line-height: 1;
  font-family: 'Rajdhani', 'SF Mono', 'Consolas', monospace;
}

.score-sub {
  display: block;
  margin-top: 4px;
  color: #8db5c9;
  font-size: 11px;
}

.case-diagnosis {
  color: #d9f2ff;
  font-size: 13px;
  line-height: 1.6;
  padding: 10px 12px;
  border-radius: 12px;
  background: rgba(8, 31, 49, 0.7);
  border: 1px solid rgba(71, 196, 255, 0.1);
}

.match-chip {
  background: rgba(10, 39, 58, 0.88);
  color: #b8f4ff;
}

.case-foot {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 18px;
  color: #88b6c8;
  font-size: 12px;
}

.similar-empty {
  padding: 24px 16px;
  border-radius: 14px;
  border: 1px solid rgba(80, 199, 255, 0.12);
  background: rgba(7, 20, 34, 0.92);
  color: #9bcde0;
  font-size: 13px;
  text-align: center;
}

.similar-empty--error {
  color: #fda4af;
  border-color: rgba(251, 113, 133, 0.18);
.similar-empty--warn,
.similar-soft-notice {
  color: #fcd34d;
  border: 1px solid rgba(250, 204, 21, 0.2);
  background: rgba(64, 46, 5, 0.34);
}

.similar-soft-notice {
  padding: 12px 14px;
  border-radius: 14px;
  font-size: 12px;
  line-height: 1.6;
}
}

@media (max-width: 1200px) {
  .kpi-strip {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 768px) {
  .kpi-strip {
    grid-template-columns: 1fr;
  }

  .outcome-strip {
    flex-direction: column;
  }

  .case-card-head {
    flex-direction: column;
  }

  .score-box {
    width: 100%;
    text-align: left;
  }
}
</style>
