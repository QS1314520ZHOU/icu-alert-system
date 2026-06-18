<template>
  <section class="device-hai-panel">
    <div class="device-hai-panel__head">
      <div>
        <div class="device-hai-panel__kicker">装置 × 院感防控清单</div>
        <div class="device-hai-panel__title">装置必要性与感染预防联动</div>
      </div>
      <button type="button" class="device-hai-panel__action" @click="emit('open-alerts')">查看相关预警</button>
    </div>

    <div class="device-hai-panel__grid">
      <article
        v-for="item in rows"
        :key="item.key"
        :class="['device-hai-panel__card', `is-${item.tone}`, { 'is-clickable': item.alertTypes.length }]"
        @click="item.alertTypes.length ? emit('focus-alert-types', item.alertTypes, item.organKey) : undefined"
      >
        <div class="device-hai-panel__card-head">
          <div>
            <div class="device-hai-panel__card-title">{{ item.title }}</div>
            <div class="device-hai-panel__card-sub">{{ item.subtitle }}</div>
          </div>
          <span :class="['device-hai-panel__badge', `is-${item.tone}`]">{{ item.statusText }}</span>
        </div>
        <div class="device-hai-panel__metric-row">
          <span v-for="chip in item.chips" :key="chip" class="device-hai-panel__chip">{{ chip }}</span>
        </div>
        <div class="device-hai-panel__summary">{{ item.summary }}</div>
        <div v-if="item.alertEntries.length" class="device-hai-panel__alert-block">
          <div class="device-hai-panel__alert-title">命中告警</div>
          <button
            v-for="(entry, idx) in item.alertEntries"
            :key="`${item.key}-alert-${idx}`"
            type="button"
            class="device-hai-panel__alert-item"
            @click.stop="emit('focus-alert-types', [entry.type], item.organKey)"
          >
            <span>{{ entry.name }}</span>
            <small>{{ entry.time }}</small>
          </button>
        </div>
        <ul v-if="item.bullets.length" class="device-hai-panel__list">
          <li v-for="(bullet, idx) in item.bullets" :key="`${item.key}-${idx}`">{{ bullet }}</li>
        </ul>
        <div class="device-hai-panel__foot">
          <button
            v-if="item.alertTypes.length"
            type="button"
            class="device-hai-panel__link"
            @click.stop="emit('focus-alert-types', item.alertTypes, item.organKey)"
          >
            定位相关预警
          </button>
          <span v-else class="device-hai-panel__empty">当前无相关装置预警</span>
        </div>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  alerts: any[]
  markers: Array<{ key: string; label: string; daysText?: string; detail?: string; severity: string }>
}>()

const emit = defineEmits<{
  (e: 'open-alerts'): void
  (e: 'focus-alert-types', types: string[], organKey?: string): void
}>()

function severityRank(value: any) {
  return ({ normal: 0, warning: 1, high: 2, critical: 3 } as Record<string, number>)[String(value || 'normal').toLowerCase()] || 0
}

function toneFromAlerts(alerts: any[], fallback = 'normal') {
  const tone = alerts.reduce((current, row) => {
    const next = String(row?.severity || fallback).toLowerCase()
    return severityRank(next) > severityRank(current) ? next : current
  }, fallback)
  return tone
}

function latestByTypes(types: string[]) {
  return (Array.isArray(props.alerts) ? props.alerts : [])
    .filter((row: any) => types.includes(String(row?.alert_type || '').toLowerCase()))
    .sort((a: any, b: any) => new Date(b?.created_at || 0).getTime() - new Date(a?.created_at || 0).getTime())
}

function markerLike(tokens: string[]) {
  return props.markers.find((row) => tokens.some((token) => String(row?.label || '').toLowerCase().includes(token)))
}

function explanationText(alert: any) {
  const explanation = alert?.explanation
  if (explanation && typeof explanation === 'object') {
    return String(explanation?.summary || explanation?.suggestion || '').trim()
  }
  return String(alert?.name || '').trim()
}

function alertEntryRows(rows: any[]) {
  return rows.slice(0, 4).map((row: any) => ({
    type: String(row?.alert_type || '').trim(),
    name: String(row?.name || row?.rule_id || row?.alert_type || '预警').trim(),
    time: formatAlertTime(row?.created_at),
  }))
}

function formatAlertTime(value: any) {
  const date = new Date(value || 0)
  if (!Number.isFinite(date.getTime())) return '时间未知'
  const month = `${date.getMonth() + 1}`.padStart(2, '0')
  const day = `${date.getDate()}`.padStart(2, '0')
  const hours = `${date.getHours()}`.padStart(2, '0')
  const minutes = `${date.getMinutes()}`.padStart(2, '0')
  return `${month}-${day} ${hours}:${minutes}`
}

const rows = computed(() => {
  const cvcMarker = markerLike(['cvc', 'picc'])
  const foleyMarker = markerLike(['foley'])
  const ettMarker = markerLike(['ett'])

  const cvcAlerts = latestByTypes(['cvc_review', 'clabsi_bundle_review', 'clabsi_suspected', 'device_position_abnormal'])
  const foleyAlerts = latestByTypes(['foley_review', 'cauti_risk'])
  const ettAlerts = latestByTypes(['ett_extubation_delay', 'vap_bundle_missing'])

  return [
    {
      key: 'cvc',
      organKey: 'circulatory',
      title: '中心静脉导管 / CLABSI',
      subtitle: cvcMarker?.detail || '用于评估导管必要性、位置与血流感染风险',
      tone: toneFromAlerts(cvcAlerts, cvcMarker?.severity || 'normal'),
      statusText: cvcAlerts.length ? '需复核' : (cvcMarker ? '持续巡视' : '未识别'),
      alertTypes: Array.from(new Set(cvcAlerts.map((row: any) => String(row?.alert_type || '').trim()).filter(Boolean))),
      alertEntries: alertEntryRows(cvcAlerts),
      chips: [cvcMarker?.daysText, cvcAlerts[0]?.extra?.bundle ? `清单 ${cvcAlerts[0].extra.bundle}` : '', cvcAlerts.length ? `${cvcAlerts.length} 条提醒` : ''].filter(Boolean),
      summary: explanationText(cvcAlerts[0]) || '暂未触发中心静脉导管相关 HAI / 装置管理提醒。',
      bullets: [
        cvcAlerts[0]?.extra?.blood_culture ? '已出现血培养阳性线索，需结合导管相关感染排查。' : '',
        cvcAlerts[0]?.alert_type === 'device_position_abnormal' ? '影像提示导管位置异常，建议优先复核尖端位置。' : '',
      ].filter(Boolean),
    },
    {
      key: 'foley',
      organKey: 'renal',
      title: '导尿管 / CAUTI',
      subtitle: foleyMarker?.detail || '联动导尿管留置与尿路感染预防',
      tone: toneFromAlerts(foleyAlerts, foleyMarker?.severity || 'normal'),
      statusText: foleyAlerts.length ? '待评估' : (foleyMarker ? '持续巡视' : '未识别'),
      alertTypes: Array.from(new Set(foleyAlerts.map((row: any) => String(row?.alert_type || '').trim()).filter(Boolean))),
      alertEntries: alertEntryRows(foleyAlerts),
      chips: [foleyMarker?.daysText, foleyAlerts[0]?.extra?.foley_hours != null ? `${fOleyHoursText(foleyAlerts[0].extra.foley_hours)}` : '', foleyAlerts.length ? `${foleyAlerts.length} 条提醒` : ''].filter(Boolean),
      summary: explanationText(foleyAlerts[0]) || '暂未触发导尿管相关 HAI / 装置管理提醒。',
      bullets: [
        foleyAlerts[0]?.extra?.urine_abnormal ? '已出现尿检异常线索，建议复核留置必要性与送检策略。' : '',
      ].filter(Boolean),
    },
    {
      key: 'ett',
      organKey: 'respiratory',
      title: '气管插管 / VAP 预防清单',
      subtitle: ettMarker?.detail || '联动气道装置留置、拔管时机与 VAP 缺项',
      tone: toneFromAlerts(ettAlerts, ettMarker?.severity || 'normal'),
      statusText: ettAlerts.length ? '需跟进' : (ettMarker ? '持续巡视' : '未识别'),
      alertTypes: Array.from(new Set(ettAlerts.map((row: any) => String(row?.alert_type || '').trim()).filter(Boolean))),
      alertEntries: alertEntryRows(ettAlerts),
      chips: [ettMarker?.daysText, ettAlerts[0]?.extra?.vent_days != null ? `通气 D${ettAlerts[0].extra.vent_days}` : '', ettAlerts.length ? `${ettAlerts.length} 条提醒` : ''].filter(Boolean),
      summary: explanationText(ettAlerts[0]) || '暂未触发气管插管相关 HAI / 装置管理提醒。',
      bullets: [
        ...(Array.isArray(ettAlerts[0]?.extra?.missing_items) ? ettAlerts[0].extra.missing_items.map((item: any) => `VAP 预防清单缺项：${item}`) : []),
      ].filter(Boolean),
    },
  ]
})

function fOleyHoursText(value: any) {
  const num = Number(value)
  if (!Number.isFinite(num)) return ''
  return `留置 ${num.toFixed(num >= 24 ? 0 : 1)}h`
}
</script>

<style scoped>
.device-hai-panel {
  display: grid;
  gap: 12px;
  margin-bottom: 16px;
  padding: 14px;
  border-radius: 14px;
  background: linear-gradient(180deg, rgba(7,20,34,.96) 0%, rgba(4,12,22,.98) 100%);
  border: 1px solid rgba(80,199,255,.14);
  box-shadow: inset 0 1px 0 rgba(145,228,255,.04), 0 12px 28px rgba(0,0,0,.2);
}
.device-hai-panel__head,
.device-hai-panel__card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}
.device-hai-panel__kicker {
  color: #7ed6eb;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: .14em;
  text-transform: uppercase;
}
.device-hai-panel__title,
.device-hai-panel__card-title {
  color: #effcff;
  font-weight: 800;
}
.device-hai-panel__title { margin-top: 4px; font-size: 18px; }
.device-hai-panel__card-title { font-size: 15px; }
.device-hai-panel__card-sub,
.device-hai-panel__summary,
.device-hai-panel__list,
.device-hai-panel__chip {
  color: #8fb8ca;
  font-size: 12px;
}
.device-hai-panel__action,
.device-hai-panel__badge,
.device-hai-panel__chip {
  display: inline-flex;
  align-items: center;
  min-height: 30px;
  padding: 0 10px;
  border-radius: 999px;
}
.device-hai-panel__action {
  border: 1px solid rgba(110,231,249,.28);
  background: linear-gradient(180deg, rgba(10,92,118,.94) 0%, rgba(8,55,74,.96) 100%);
  color: #effcff;
  cursor: pointer;
}
.device-hai-panel__grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}
.device-hai-panel__card {
  display: grid;
  gap: 10px;
  padding: 12px;
  border-radius: 12px;
  background: rgba(8, 28, 44, 0.72);
  border: 1px solid rgba(80,199,255,.12);
}
.device-hai-panel__card.is-warning,
.device-hai-panel__badge.is-warning { border-color: rgba(245,158,11,.22); }
.device-hai-panel__card.is-high,
.device-hai-panel__badge.is-high { border-color: rgba(249,115,22,.24); }
.device-hai-panel__card.is-critical,
.device-hai-panel__badge.is-critical { border-color: rgba(244,63,94,.28); }
.device-hai-panel__badge {
  border: 1px solid rgba(80,199,255,.14);
  background: rgba(12, 36, 54, 0.9);
  color: #dffbff;
  font-size: 12px;
}
.device-hai-panel__metric-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.device-hai-panel__chip {
  background: rgba(6, 20, 33, 0.92);
  border: 1px solid rgba(104, 193, 229, 0.18);
}
.device-hai-panel__summary {
  line-height: 1.6;
}
.device-hai-panel__alert-block {
  display: grid;
  gap: 6px;
}
.device-hai-panel__alert-title {
  color: #dffbff;
  font-size: 12px;
  font-weight: 700;
}
.device-hai-panel__alert-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 10px;
  border-radius: 10px;
  border: 1px solid rgba(104, 193, 229, 0.14);
  background: rgba(6, 20, 33, 0.92);
  cursor: pointer;
  text-align: left;
}
.device-hai-panel__alert-item span {
  color: #d8ebf4;
  font-size: 11px;
  line-height: 1.5;
}
.device-hai-panel__alert-item small {
  color: #7fa0b3;
  font-size: 10px;
  white-space: nowrap;
}
.device-hai-panel__list {
  margin: 0;
  padding-left: 18px;
  line-height: 1.6;
}
.device-hai-panel__foot {
  display: flex;
  align-items: center;
  justify-content: flex-end;
}
.device-hai-panel__card.is-clickable {
  cursor: pointer;
  transition: transform .2s ease, box-shadow .2s ease, border-color .2s ease;
}
.device-hai-panel__card.is-clickable:hover {
  transform: translateY(-1px);
  box-shadow: 0 10px 18px rgba(0,0,0,.16);
  border-color: rgba(110,231,249,.24);
}
.device-hai-panel__link,
.device-hai-panel__empty {
  font-size: 12px;
}
.device-hai-panel__link {
  border: 0;
  background: transparent;
  color: #7ed6eb;
  cursor: pointer;
  padding: 0;
  font-weight: 700;
}
.device-hai-panel__empty {
  color: #64889a;
}
@media (max-width: 980px) {
  .device-hai-panel__grid {
    grid-template-columns: 1fr;
  }
}
html[data-theme='light'] .device-hai-panel {
  background: linear-gradient(180deg, rgba(246,250,253,.98) 0%, rgba(239,246,250,.98) 100%);
  border-color: rgba(130, 170, 194, 0.24);
}
html[data-theme='light'] .device-hai-panel__title,
html[data-theme='light'] .device-hai-panel__card-title {
  color: #17324a;
}
html[data-theme='light'] .device-hai-panel__kicker,
html[data-theme='light'] .device-hai-panel__card-sub,
html[data-theme='light'] .device-hai-panel__summary,
html[data-theme='light'] .device-hai-panel__alert-item small,
html[data-theme='light'] .device-hai-panel__list,
html[data-theme='light'] .device-hai-panel__chip {
  color: #56748d;
}
html[data-theme='light'] .device-hai-panel__card,
html[data-theme='light'] .device-hai-panel__badge,
html[data-theme='light'] .device-hai-panel__chip,
html[data-theme='light'] .device-hai-panel__alert-item {
  background: rgba(255,255,255,.94);
  border-color: rgba(130, 170, 194, 0.24);
}
html[data-theme='light'] .device-hai-panel__alert-title,
html[data-theme='light'] .device-hai-panel__alert-item span {
  color: #17324a;
}
html[data-theme='light'] .device-hai-panel__link {
  color: #1f6f94;
}
html[data-theme='light'] .device-hai-panel__empty {
  color: #7b93a7;
}
</style>
