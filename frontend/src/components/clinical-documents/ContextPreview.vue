<template>
  <div class="context-preview">
    <div class="cp-header">
      <span class="cp-title">📋 原始数据上下文</span>
      <span v-if="ctx" class="cp-window">{{ ctx.window_start }} ~ {{ ctx.window_end }}</span>
    </div>

    <template v-if="ctx">
      <section class="cp-section">
        <h4 class="cp-section-title">患者</h4>
        <div class="cp-kv">
          <span>{{ ctx.basics?.bed }}床</span>
          <span>{{ ctx.basics?.age }}岁 {{ ctx.basics?.sex }}</span>
          <span>入科第{{ ctx.basics?.day }}天</span>
        </div>
        <div class="cp-diagnosis">{{ ctx.basics?.diagnosis }}</div>
      </section>

      <section class="cp-section">
        <h4 class="cp-section-title">生命体征 [V]</h4>
        <div class="cp-vital-grid">
          <div v-for="(stat, key) in vitalItems" :key="key" class="cp-vital-item">
            <span class="cp-vital-label">{{ key }}</span>
            <span class="cp-vital-value">{{ stat.min == null || stat.max == null ? '—' : `${stat.min}~${stat.max}` }}</span>
            <span :class="['cp-vital-trend', `is-${trendTone(stat.trend)}`]">{{ stat.trend }}</span>
          </div>
        </div>
        <div v-if="ctx.v?.events?.length" class="cp-events">
          <span v-for="(ev, i) in ctx.v.events" :key="i" class="cp-event-chip">
            {{ ev.time_hm }} {{ ev.type }}({{ ev.value }})
          </span>
        </div>
      </section>

      <section v-if="ctx.labs?.length" class="cp-section">
        <h4 class="cp-section-title">化验 ({{ ctx.labs.length }}项)</h4>
        <div v-for="l in ctx.labs" :key="l.id" class="cp-lab-row">
          <span class="cp-lab-id">[L{{ l.id }}]</span>
          <span class="cp-lab-name">{{ l.name }}</span>
          <span class="cp-lab-value">{{ l.prev }}→{{ l.curr }}{{ l.unit }}</span>
          <span :class="['cp-lab-flag', flagClass(l.flag)]">{{ l.flag }}</span>
        </div>
      </section>

      <section v-if="ctx.drugs?.length" class="cp-section">
        <h4 class="cp-section-title">用药 ({{ ctx.drugs.length }}条)</h4>
        <div v-for="d in ctx.drugs" :key="d.id" class="cp-drug-row">
          <span class="cp-drug-id">[D{{ d.id }}]</span>
          <span>{{ d.time_hm }} {{ d.action }} {{ d.name }}</span>
          <span v-if="d.dose_after" class="cp-drug-dose">{{ d.dose_after }}</span>
        </div>
      </section>

      <section v-if="ctx.vent" class="cp-section">
        <h4 class="cp-section-title">呼吸机 [VT0]</h4>
        <div class="cp-kv">
          <span>{{ ctx.vent.mode }}</span>
          <span>FiO2 {{ ctx.vent.fio2 }}</span>
          <span>PEEP {{ ctx.vent.peep }}</span>
          <span>VT {{ ctx.vent.vt }}</span>
          <span>P/F {{ ctx.vent.pf_ratio }}</span>
        </div>
      </section>

      <section v-if="ctx.alerts?.length" class="cp-section">
        <h4 class="cp-section-title">告警 ({{ ctx.alerts.length }}种)</h4>
        <div v-for="a in ctx.alerts" :key="a.id" class="cp-alert-row">
          <span class="cp-alert-id">[A{{ a.id }}]</span>
          <span>{{ a.type }} {{ a.severity }} ×{{ a.count }}</span>
          <span :class="['cp-alert-status', a.active ? 'is-active' : 'is-resolved']">
            {{ a.active ? '持续' : '已缓解' }}
          </span>
        </div>
      </section>

      <section v-if="ctx.scores" class="cp-section">
        <h4 class="cp-section-title">评分 [AS1]</h4>
        <div class="cp-kv">
          <span>GCS {{ ctx.scores.gcs }}</span>
          <span>SOFA {{ ctx.scores.sofa }}</span>
          <span>APACHE {{ ctx.scores.apache }}</span>
        </div>
      </section>
    </template>

    <div v-else class="cp-empty">等待生成…</div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ context: any }>()

const ctx = computed(() => props.context)

const vitalItems = computed(() => {
  if (!ctx.value?.v) return {}
  const v = ctx.value.v
  return { HR: v.hr, MAP: v.map, SpO2: v.spo2, T: v.temp, RR: v.rr }
})

function trendTone(trend: string) {
  if (trend === '上升' || trend === '下降') return 'warn'
  if (trend === '波动') return 'danger'
  if (trend === '无数据' || trend === '数据不足') return 'muted'
  return 'ok'
}

function flagClass(flag: string) {
  if (flag.includes('↑↑') || flag.includes('↓↓')) return 'is-critical'
  if (flag.includes('↑') || flag.includes('↓')) return 'is-abnormal'
  return ''
}
</script>

<style scoped>
.context-preview {
  font-size: 12px;
  color: #333;
}
.cp-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.cp-title {
  font-weight: 600;
  font-size: 14px;
}
.cp-window {
  font-size: 11px;
  color: #8c8c8c;
}
.cp-section {
  margin-bottom: 14px;
  padding-bottom: 10px;
  border-bottom: 1px solid #f0f0f0;
}
.cp-section-title {
  font-size: 12px;
  font-weight: 600;
  color: #1677ff;
  margin: 0 0 6px;
}
.cp-kv {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 12px;
}
.cp-kv span {
  background: #f5f5f5;
  padding: 2px 8px;
  border-radius: 4px;
}
.cp-diagnosis {
  margin-top: 4px;
  color: #595959;
  line-height: 1.5;
}
.cp-vital-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 4px;
}
.cp-vital-item {
  display: flex;
  align-items: center;
  gap: 6px;
}
.cp-vital-label {
  font-weight: 600;
  min-width: 36px;
}
.cp-vital-value {
  color: #595959;
}
.cp-vital-trend {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 3px;
}
.cp-vital-trend.is-ok { background: #f6ffed; color: #52c41a; }
.cp-vital-trend.is-warn { background: #fff7e6; color: #fa8c16; }
.cp-vital-trend.is-danger { background: #fff1f0; color: #ff4d4f; }
.cp-vital-trend.is-muted { background: #f5f5f5; color: #8c8c8c; }
.cp-events {
  margin-top: 6px;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.cp-event-chip {
  background: #fff1f0;
  color: #cf1322;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
}
.cp-lab-row, .cp-drug-row, .cp-alert-row {
  display: flex;
  gap: 6px;
  align-items: center;
  padding: 2px 0;
  line-height: 1.6;
}
.cp-lab-id, .cp-drug-id, .cp-alert-id {
  color: #1677ff;
  font-weight: 600;
  font-size: 11px;
}
.cp-lab-name { font-weight: 500; }
.cp-lab-value { color: #595959; }
.cp-lab-flag.is-critical { color: #ff4d4f; font-weight: 700; }
.cp-lab-flag.is-abnormal { color: #fa8c16; font-weight: 600; }
.cp-drug-dose { color: #8c8c8c; }
.cp-alert-status {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 3px;
}
.cp-alert-status.is-active { background: #fff1f0; color: #ff4d4f; }
.cp-alert-status.is-resolved { background: #f6ffed; color: #52c41a; }
.cp-empty {
  text-align: center;
  color: #bfbfbf;
  padding: 40px 0;
}

/* ================= Dark Theme Overrides ================= */
:global(.theme-dark) .context-preview {
  color: #d9e6f3;
}
:global(.theme-dark) .cp-window {
  color: #7f93ab;
}
:global(.theme-dark) .cp-section {
  border-bottom: 1px solid rgba(125, 167, 214, 0.14);
}
:global(.theme-dark) .cp-section-title {
  color: #22d3ee;
}
:global(.theme-dark) .cp-kv span {
  background: #091827;
  color: #d9e6f3;
}
:global(.theme-dark) .cp-diagnosis {
  color: #7f93ab;
}
:global(.theme-dark) .cp-vital-value {
  color: #b0c4de;
}
:global(.theme-dark) .cp-vital-trend.is-ok { background: rgba(52, 211, 153, 0.15); color: #34d399; }
:global(.theme-dark) .cp-vital-trend.is-warn { background: rgba(245, 158, 11, 0.15); color: #f59e0b; }
:global(.theme-dark) .cp-vital-trend.is-danger { background: rgba(239, 68, 68, 0.15); color: #f87171; }
:global(.theme-dark) .cp-vital-trend.is-muted { background: rgba(125, 167, 214, 0.1); color: #586b82; }
:global(.theme-dark) .cp-event-chip {
  background: rgba(239, 68, 68, 0.18);
  color: #fca5a5;
}
:global(.theme-dark) .cp-lab-id,
:global(.theme-dark) .cp-drug-id,
:global(.theme-dark) .cp-alert-id {
  color: #38bdf8;
}
:global(.theme-dark) .cp-lab-value {
  color: #b0c4de;
}
:global(.theme-dark) .cp-lab-flag.is-critical { color: #f87171; }
:global(.theme-dark) .cp-lab-flag.is-abnormal { color: #fbbf24; }
:global(.theme-dark) .cp-drug-dose {
  color: #7f93ab;
}
:global(.theme-dark) .cp-alert-status.is-active { background: rgba(239, 68, 68, 0.15); color: #f87171; }
:global(.theme-dark) .cp-alert-status.is-resolved { background: rgba(52, 211, 153, 0.15); color: #34d399; }
:global(.theme-dark) .cp-empty {
  color: #586b82;
}
</style>
