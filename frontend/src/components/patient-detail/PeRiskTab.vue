<template>
  <section class="pe-tab">
    <div class="pe-hero">
      <div>
        <div class="pe-title">肺栓塞检测 / Wells 评分</div>
        <div class="pe-sub">把疑似肺栓塞模式识别与 Wells 中高危评分合并展示，避免淹没在普通预警流里。</div>
      </div>
      <div class="pe-pill">{{ headline }}</div>
    </div>

    <div class="pe-grid">
      <article class="pe-card">
        <div class="pe-card-title">疑似肺栓塞模式</div>
        <div class="pe-card-main">{{ suspectedMain }}</div>
        <div class="pe-card-meta">{{ suspectedMeta }}</div>
        <div v-if="suspectedChips.length" class="pe-chip-row">
          <span v-for="(chip, idx) in suspectedChips" :key="`sus-${idx}`" class="pe-chip">{{ chip }}</span>
        </div>
      </article>
      <article class="pe-card">
        <div class="pe-card-title">Wells 评分</div>
        <div class="pe-card-main">{{ wellsMain }}</div>
        <div class="pe-card-meta">{{ wellsMeta }}</div>
        <div v-if="wellsChips.length" class="pe-chip-row">
          <span v-for="(chip, idx) in wellsChips" :key="`wel-${idx}`" class="pe-chip">{{ chip }}</span>
        </div>
      </article>
    </div>

    <div v-if="alerts.length" class="pe-list">
      <article v-for="(item, idx) in alerts.slice(0, 6)" :key="item._id || idx" class="pe-row">
        <div>
          <strong>{{ item.name || '肺栓塞提示' }}</strong>
          <div class="pe-row-time">{{ fmtTime(item.created_at) || '时间未知' }}</div>
        </div>
        <div class="pe-row-main">{{ item.explanation?.summary || item.extra?.suggestion || '暂无结构化摘要' }}</div>
      </article>
    </div>
    <div v-else class="pe-empty">暂无肺栓塞检测相关预警</div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
const props = defineProps<{ alerts: Array<any>; fmtTime: (v: any) => string }>()
const suspectedAlert = computed(() => props.alerts.find((row) => String(row?.alert_type || '') === 'pe_suspected'))
const wellsAlert = computed(() => props.alerts.find((row) => String(row?.alert_type || '') === 'pe_wells_high'))
const headline = computed(() => suspectedAlert.value?.name || wellsAlert.value?.name || '等待肺栓塞风险识别')
const suspectedMain = computed(() => suspectedAlert.value?.explanation?.summary || suspectedAlert.value?.name || '当前未触发疑似肺栓塞模式识别')
const suspectedMeta = computed(() => suspectedAlert.value ? (props.fmtTime(suspectedAlert.value.created_at) || '最近识别') : '当前无模式识别告警')
const suspectedChips = computed(() => { const extra = suspectedAlert.value?.extra || {}; const rows = [Array.isArray(extra?.matched_criteria) ? `匹配 ${extra.matched_criteria.length} 项` : '', extra?.ddimer != null ? `D-Dimer ${extra.ddimer}` : '', extra?.wells_score != null ? `Wells ${extra.wells_score}` : '', extra?.suggestion || '']; return rows.filter(Boolean) })
const wellsMain = computed(() => wellsAlert.value?.explanation?.summary || wellsAlert.value?.name || '当前未触发 Wells 中高危提醒')
const wellsMeta = computed(() => { const score = wellsAlert.value?.extra?.wells_score ?? wellsAlert.value?.value; return score != null ? `当前分值 ${score}` : (wellsAlert.value ? (props.fmtTime(wellsAlert.value.created_at) || '最近识别') : '待评分') })
const wellsChips = computed(() => { const rows = Array.isArray(wellsAlert.value?.extra?.wells_items) ? wellsAlert.value.extra.wells_items : []; return rows.slice(0, 4).map((item: any) => `${item?.label || item?.factor || '条目'} ${item?.score ?? ''}`.trim()).filter(Boolean) })
</script>

<style scoped>
.pe-tab { display: grid; gap: 14px; }
.pe-hero { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; flex-wrap: wrap; }
.pe-title { color: var(--text-primary); font-size: 22px; font-weight: 800; }
.pe-sub,.pe-card-meta,.pe-row-time { color: var(--text-secondary); font-size: 12px; }
.pe-pill { padding: 10px 14px; border-radius: var(--card-radius); background: var(--bg-surface), 0.68); color: var(--danger-soft); border: 1px solid rgba(251, 113, 133, 0.16); }
.pe-grid,.pe-list { display: grid; gap: 12px; }
.pe-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.pe-card,.pe-row { padding: 16px; border-radius: var(--card-radius); border: 1px solid rgba(251, 113, 133, 0.14); background: var(--bg-surface), var(--bg-surface)); }
.pe-card-title { color: #ffe4e6; font-size: 15px; font-weight: 800; }
.pe-card-main,.pe-row-main { margin-top: 10px; color: var(--danger-bg); line-height: 1.6; }
.pe-chip-row { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }
.pe-chip { padding: 6px 10px; border-radius: var(--card-radius); background: var(--bg-surface), 0.72); color: #ffe4e6; border: 1px solid rgba(251, 113, 133, 0.14); font-size: 12px; }
.pe-row { display: grid; grid-template-columns: 200px 1fr; gap: 14px; }
.pe-row strong { color: var(--danger-bg); }
.pe-empty { padding: 24px; text-align: center; color: #caa3ad; border: 1px dashed rgba(251, 113, 133, 0.18); border-radius: var(--card-radius); }
html[data-theme='light'] .pe-title {
  color: var(--text-secondary);
}
html[data-theme='light'] .pe-sub,
html[data-theme='light'] .pe-card-meta,
html[data-theme='light'] .pe-row-time {
  color: var(--text-secondary);
}
html[data-theme='light'] .pe-pill {
  color: var(--danger-strong);
  background: var(--bg-surface) 0%, rgba(255, 233, 239, 0.98) 100%);
  border-color: rgba(251, 113, 133, 0.28);
  box-shadow: var(--card-shadow);
}
html[data-theme='light'] .pe-card,
html[data-theme='light'] .pe-row {
  border-color: rgba(198, 212, 226, 0.92);
  background:
    var(--bg-surface), rgba(59, 130, 246, 0) 38%),
    var(--bg-surface) 0%, rgba(245, 249, 253, 0.99) 100%);
  box-shadow: var(--card-shadow);
}
html[data-theme='light'] .pe-card-title,
html[data-theme='light'] .pe-card-main,
html[data-theme='light'] .pe-row strong,
html[data-theme='light'] .pe-row-main {
  color: var(--text-secondary);
}
html[data-theme='light'] .pe-chip {
  color: var(--brand);
  background: rgba(239, 246, 255, 0.98);
  border-color: rgba(59, 130, 246, 0.18);
}
html[data-theme='light'] .pe-empty {
  color: var(--text-secondary);
  background: rgba(248, 251, 255, 0.98);
  border-color: rgba(198, 212, 226, 0.92);
}
@media (max-width: 900px) { .pe-grid,.pe-row { grid-template-columns: 1fr; } }
</style>

