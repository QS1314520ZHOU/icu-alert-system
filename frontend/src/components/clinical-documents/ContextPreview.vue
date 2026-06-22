<template>
  <div class="context-preview">
    <div class="cp-header">
      <span class="cp-title">原始数据上下文</span>
      <span v-if="ctx" class="cp-window">{{ ctx.window_start }} ~ {{ ctx.window_end }}</span>
    </div>

    <template v-if="ctx">
      <section class="cp-section">
        <h4 class="cp-section-title">患者</h4>
        <div class="cp-kv">
          <span>{{ ctx.basics?.bed || '-' }}床</span>
          <span>{{ ctx.basics?.age ?? '-' }}岁 {{ sexLabel(ctx.basics?.sex) }}</span>
          <span>入科第{{ ctx.basics?.day ?? 0 }}天</span>
        </div>
        <div class="cp-diagnosis">{{ ctx.basics?.diagnosis || '未提供诊断' }}</div>
      </section>

      <section class="cp-section">
        <h4 class="cp-section-title">生命体征 [V]</h4>
        <div class="cp-vital-grid">
          <div v-for="(stat, key) in vitalItems" :key="key" class="cp-vital-item">
            <span class="cp-vital-label">{{ key }}</span>
            <span class="cp-vital-value">{{ formatRange(stat.min, stat.max, key) }}</span>
            <span :class="['cp-vital-trend', `is-${trendTone(stat.trend)}`]">{{ trendLabel(stat.trend) }}</span>
          </div>
        </div>
        <div v-if="ctx.v?.events?.length" class="cp-events">
          <span v-for="(ev, i) in ctx.v.events" :key="i" class="cp-event-chip">
            {{ ev.time_hm }} {{ ev.type }}({{ formatClinicalValue(ev.value, valueDigits(ev.type)) }})
          </span>
        </div>
      </section>

      <section v-if="ctx.labs?.length" class="cp-section">
        <h4 class="cp-section-title">化验 ({{ ctx.labs.length }}项)</h4>
        <div v-for="l in ctx.labs" :key="l.id" class="cp-lab-row">
          <span class="cp-lab-id">[L{{ l.id }}]</span>
          <span class="cp-lab-name">{{ l.name }}</span>
          <span class="cp-lab-value">{{ formatClinicalValue(l.prev, labDigits(l.name)) }} -> {{ formatClinicalValue(l.curr, labDigits(l.name)) }}{{ l.unit }}</span>
          <span :class="['cp-lab-flag', flagClass(l.flag)]">{{ flagLabel(l.flag) }}</span>
        </div>
      </section>

      <section v-if="ctx.drugs?.length" class="cp-section">
        <h4 class="cp-section-title">用药 ({{ ctx.drugs.length }}条)</h4>
        <div v-for="d in ctx.drugs" :key="d.id" class="cp-drug-row">
          <span class="cp-drug-id">[D{{ d.id }}]</span>
          <span>{{ d.time_hm }} {{ actionLabel(d.action) }} {{ d.name }}</span>
          <span v-if="d.dose_after" class="cp-drug-dose">{{ d.dose_after }}</span>
        </div>
      </section>

      <section v-if="ctx.vent" class="cp-section">
        <h4 class="cp-section-title">呼吸机 [VT0]</h4>
        <div class="cp-kv">
          <span>{{ ctx.vent.mode }}</span>
          <span>吸氧浓度 {{ formatClinicalValue(ctx.vent.fio2, Number(ctx.vent.fio2) > 1 ? 0 : 2) }}</span>
          <span v-if="Number(ctx.vent.peep)">呼气末正压 {{ formatClinicalValue(ctx.vent.peep, 1) }}</span>
          <span v-if="Number(ctx.vent.vt)">潮气量 {{ formatClinicalValue(ctx.vent.vt, 0) }}</span>
          <span v-if="ctx.vent.pf_ratio != null">氧合指数 {{ formatClinicalValue(ctx.vent.pf_ratio, 1) }}</span>
        </div>
      </section>

      <section v-if="ctx.alerts?.length" class="cp-section">
        <h4 class="cp-section-title">告警 ({{ ctx.alerts.length }}种)</h4>
        <div v-for="a in ctx.alerts" :key="a.id" class="cp-alert-row">
          <span class="cp-alert-id">[A{{ a.id }}]</span>
          <span>{{ alertTypeLabel(a.type) }} {{ severityLabel(a.severity) }} x{{ a.count }}</span>
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

    <div v-else class="cp-empty">等待生成或选择草稿</div>
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

function formatClinicalValue(value: any, digits = 1) {
  if (value == null || value === '') return '-'
  const num = Number(value)
  if (!Number.isFinite(num)) return String(value)
  const rounded = Number(num.toFixed(digits))
  if (digits <= 0 || Math.abs(rounded - Math.round(rounded)) < 1e-9) return String(Math.round(rounded))
  return rounded.toFixed(digits).replace(/\.?0+$/, '')
}

function valueDigits(label: any) {
  const text = String(label || '').toLowerCase()
  if (text.includes('temp') || text.includes('体温') || text === 't') return 1
  if (text.includes('fio2')) return 0
  return 0
}

function labDigits(name: any) {
  const text = String(name || '').toLowerCase()
  if (text.includes('钾') || text.includes('k') || text.includes('乳酸') || text.includes('lac')) return 1
  if (text.includes('pct')) return 2
  return 1
}

function formatRange(min: any, max: any, label: any) {
  if (min == null || max == null) return '-'
  const digits = valueDigits(label)
  return `${formatClinicalValue(min, digits)}~${formatClinicalValue(max, digits)}`
}

function sexLabel(raw: string) {
  const value = String(raw || '').trim().toLowerCase()
  if (['male', 'm', 'man', '男'].includes(value)) return '男'
  if (['female', 'f', 'woman', '女'].includes(value)) return '女'
  return raw || '未知'
}

function trendLabel(trend: string) {
  const map: Record<string, string> = {
    up: '上升',
    down: '下降',
    stable: '平稳',
    volatile: '波动',
    no_data: '无数据',
    insufficient: '数据不足',
  }
  return map[trend] || trend || '-'
}

function trendTone(trend: string) {
  const label = trendLabel(trend)
  if (label === '上升' || label === '下降') return 'warn'
  if (label === '波动') return 'danger'
  if (label === '无数据' || label === '数据不足') return 'muted'
  return 'ok'
}

function flagLabel(flag: string) {
  const value = String(flag || '')
  const map: Record<string, string> = {
    critical_high: '危急高',
    high: '偏高',
    normal: '正常',
    low: '偏低',
    critical_low: '危急低',
    '↑↑': '危急高',
    '↑': '偏高',
    '→': '正常',
    '↓': '偏低',
    '↓↓': '危急低',
  }
  return map[value] || value || '-'
}

function flagClass(flag: string) {
  const label = flagLabel(flag)
  if (label.includes('危急')) return 'is-critical'
  if (label.includes('偏高') || label.includes('偏低')) return 'is-abnormal'
  return ''
}

function actionLabel(action: string) {
  const map: Record<string, string> = {
    new: '新增',
    stop: '停用',
    increase: '升剂量',
    decrease: '降剂量',
  }
  return map[action] || action
}

function severityLabel(severity: string) {
  const map: Record<string, string> = {
    critical: '危急',
    high: '高危',
    medium: '中危',
    low: '低危',
  }
  return map[String(severity || '').toLowerCase()] || severity || ''
}

function alertTypeLabel(type: string) {
  const map: Record<string, string> = {
    aki: '急性肾损伤',
    sepsis: '脓毒症',
    hypotension: '低血压',
    hypoxemia: '低氧',
  }
  return map[String(type || '').toLowerCase()] || type || ''
}
</script>

<style scoped>
.context-preview {
  font-size: 12px;
  color: var(--text-secondary);
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
  color: var(--text-muted);
}
.cp-section {
  margin-bottom: 14px;
  padding-bottom: 10px;
  border-bottom: 1px solid #edf1f7;
}
.cp-section-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--brand);
  margin: 0 0 6px;
}
.cp-kv {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 12px;
}
.cp-kv span {
  background: var(--bg-surface-2);
  padding: 2px 8px;
  border-radius: var(--card-radius);
}
.cp-diagnosis {
  margin-top: 4px;
  color: var(--text-muted);
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
  color: var(--text-muted);
}
.cp-vital-trend {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: var(--card-radius);
}
.cp-vital-trend.is-ok { background: var(--bg-surface); color: var(--success); }
.cp-vital-trend.is-warn { background: var(--warning-soft); color: var(--warning); }
.cp-vital-trend.is-danger { background: var(--danger-bg); color: var(--danger); }
.cp-vital-trend.is-muted { background: var(--bg-surface-2); color: var(--text-muted); }
.cp-events {
  margin-top: 6px;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.cp-event-chip {
  background: var(--danger-bg);
  color: #b42318;
  padding: 2px 8px;
  border-radius: var(--card-radius);
  font-size: 11px;
}
.cp-lab-row,
.cp-drug-row,
.cp-alert-row {
  display: flex;
  gap: 6px;
  align-items: center;
  padding: 2px 0;
  line-height: 1.6;
}
.cp-lab-id,
.cp-drug-id,
.cp-alert-id {
  color: var(--brand);
  font-weight: 600;
  font-size: 11px;
}
.cp-lab-name { font-weight: 500; }
.cp-lab-value { color: var(--text-muted); }
.cp-lab-flag.is-critical { color: var(--danger); font-weight: 700; }
.cp-lab-flag.is-abnormal { color: var(--warning); font-weight: 600; }
.cp-drug-dose { color: var(--text-muted); }
.cp-alert-status {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: var(--card-radius);
}
.cp-alert-status.is-active { background: var(--danger-bg); color: var(--danger); }
.cp-alert-status.is-resolved { background: var(--bg-surface); color: var(--success); }
.cp-empty {
  text-align: center;
  color: var(--text-muted);
  padding: 40px 0;
}
</style>
