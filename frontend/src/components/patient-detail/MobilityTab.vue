<template>
  <section class="mobility-tab">
    <div class="mobility-hero">
      <div>
        <div class="mobility-title">ICU-AW / 早期活动</div>
        <div class="mobility-sub">围绕 ICU 获得性衰弱风险、制动时长和早期活动机会做专题展示。</div>
      </div>
      <div class="mobility-pill">{{ headline }}</div>
    </div>

    <div class="mobility-grid">
      <article class="mobility-card">
        <div class="mobility-card-title">ICU-AW 风险</div>
        <div class="mobility-card-main">{{ riskSummary }}</div>
        <div class="mobility-card-meta">{{ riskMeta }}</div>
        <div v-if="riskChips.length" class="mobility-chip-row">
          <span v-for="(chip, idx) in riskChips" :key="`risk-${idx}`" class="mobility-chip">{{ chip }}</span>
        </div>
      </article>
      <article class="mobility-card">
        <div class="mobility-card-title">活动时机</div>
        <div class="mobility-card-main">{{ opportunitySummary }}</div>
        <div class="mobility-card-meta">{{ opportunityMeta }}</div>
        <div v-if="opportunityChips.length" class="mobility-chip-row">
          <span v-for="(chip, idx) in opportunityChips" :key="`opp-${idx}`" class="mobility-chip">{{ chip }}</span>
        </div>
      </article>
    </div>

    <div v-if="alerts.length" class="mobility-list">
      <article v-for="(item, idx) in alerts.slice(0, 6)" :key="item._id || idx" class="mobility-row">
        <div>
          <strong>{{ item.name || '活动评估' }}</strong>
          <div class="mobility-row-time">{{ fmtTime(item.created_at) || '时间未知' }}</div>
        </div>
        <div class="mobility-row-main">{{ item.explanation?.summary || item.extra?.message || item.extra?.recommended_level_label || '暂无说明' }}</div>
      </article>
    </div>
    <div v-else class="mobility-empty">暂无 ICU-AW / 早期活动相关预警</div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
const props = defineProps<{ alerts: Array<any>; fmtTime: (v: any) => string }>()
const riskAlert = computed(() => props.alerts.find((row) => String(row?.alert_type || '') === 'icu_aw_risk'))
const oppAlert = computed(() => props.alerts.find((row) => String(row?.alert_type || '') === 'early_mobility_recommendation'))
const headline = computed(() => oppAlert.value?.extra?.recommended_level_label || (riskAlert.value ? '存在高风险信号' : '等待评估'))
const riskSummary = computed(() => riskAlert.value?.explanation?.summary || riskAlert.value?.name || '当前未见 ICU-AW 高风险提示')
const riskMeta = computed(() => riskAlert.value ? (props.fmtTime(riskAlert.value.created_at) || '最近更新') : '当前无高风险预警')
const riskChips = computed(() => { const factors = Array.isArray(riskAlert.value?.extra?.factors) ? riskAlert.value.extra.factors : []; return factors.slice(0, 4).map((item: any) => item?.evidence || item?.factor).filter(Boolean) })
const opportunitySummary = computed(() => oppAlert.value?.extra?.message || oppAlert.value?.explanation?.summary || '当前未触发活动机会提醒')
const opportunityMeta = computed(() => { const hours = oppAlert.value?.extra?.hours_since_activity; return hours != null ? `距上次活动 ${hours}h` : (oppAlert.value ? (props.fmtTime(oppAlert.value.created_at) || '最近更新') : '待活动评估') })
const opportunityChips = computed(() => { const readiness = oppAlert.value?.extra?.mobility_readiness || {}; const rows = [readiness?.recommended_level_label, readiness?.hemodynamic_status, readiness?.oxygenation_status, oppAlert.value?.extra?.immobility_hours != null ? `制动 ${oppAlert.value.extra.immobility_hours}h` : '']; return rows.filter(Boolean) })
</script>

<style scoped>
.mobility-tab { display: grid; gap: 14px; }
.mobility-hero { display: flex; justify-content: space-between; gap: 16px; flex-wrap: wrap; align-items: flex-start; }
.mobility-title { color: #effcff; font-size: 22px; font-weight: 800; }
.mobility-sub,.mobility-card-meta,.mobility-row-time { color: #8bb2c4; font-size: 12px; }
.mobility-pill { padding: 10px 14px; border-radius: 999px; background: rgba(10, 61, 87, 0.54); color: #bcecff; border: 1px solid rgba(125, 211, 252, 0.16); }
.mobility-grid,.mobility-list { display: grid; gap: 12px; }
.mobility-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.mobility-card,.mobility-row { padding: 16px; border-radius: 16px; border: 1px solid rgba(125, 211, 252, 0.12); background: linear-gradient(180deg, rgba(10, 29, 47, 0.94), rgba(7, 18, 31, 0.98)); }
.mobility-card-title { color: #dffbff; font-size: 15px; font-weight: 800; }
.mobility-card-main,.mobility-row-main { margin-top: 10px; color: #effcff; line-height: 1.6; }
.mobility-chip-row { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }
.mobility-chip { padding: 6px 10px; border-radius: 999px; background: rgba(12, 37, 57, 0.92); color: #d7f3ff; font-size: 12px; border: 1px solid rgba(125, 211, 252, 0.12); }
.mobility-row { display: grid; grid-template-columns: 200px 1fr; gap: 14px; align-items: start; }
.mobility-row strong { color: #effcff; }
.mobility-empty { padding: 24px; text-align: center; color: #8bb2c4; border: 1px dashed rgba(125, 211, 252, 0.2); border-radius: 16px; }
@media (max-width: 900px) { .mobility-grid,.mobility-row { grid-template-columns: 1fr; } }
</style>
