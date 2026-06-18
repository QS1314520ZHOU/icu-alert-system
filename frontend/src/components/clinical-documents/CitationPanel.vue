<template>
  <div class="citation-panel">
    <div class="cp-header">
      <span class="cp-title">引用依据</span>
      <span class="cp-count">{{ citations.length }} 条</span>
    </div>
    <div v-if="citations.length" class="cp-list">
      <article v-for="c in citations" :key="citationId(c)" class="cp-card">
        <div class="cp-card-ref">[{{ citationId(c) }}]</div>
        <div class="cp-card-source">{{ sourceLabel(c) }}</div>
        <div v-if="c.observed_at" class="cp-card-time">{{ c.observed_at }}</div>
        <div class="cp-card-detail">{{ detailText(c) }}</div>
      </article>
    </div>
    <div v-else class="cp-empty">暂无引用信息</div>
  </div>
</template>

<script setup lang="ts">
import type { Citation } from '../../api/clinicalDocuments'
import { formatClinicalText, formatClinicalTermLabel } from '../../utils/displayLabels'

const props = defineProps<{
  citations: Citation[]
  context: any
}>()

function citationId(item: Citation): string {
  return String(item.id || item.ref || '')
}

function sourceLabel(item: Citation): string {
  if (item.title) return formatClinicalText(item.title, '未知来源')
  const source = String(item.source || '')
  const direct: Record<string, string> = {
    vitals: '生命体征',
    ventilator_current: '呼吸机当前参数',
    vent_change: '呼吸机调整',
    scores: '评分',
  }
  if (direct[source]) return direct[source]
  if (source.startsWith('lab:')) return `化验：${formatClinicalText(source.slice(4), '检验')}`
  if (source.startsWith('drug:')) return `用药：${formatClinicalText(source.slice(5), '用药')}`
  if (source.startsWith('alert:')) return `预警：${formatClinicalTermLabel(source.slice(6), '风险提醒')}`
  const typeMap: Record<string, string> = {
    vital_sign: '生命体征',
    lab: '化验',
    medication: '用药',
    ventilator: '呼吸机',
    alert: '预警',
    score: '评分',
  }
  return typeMap[String(item.source_type || '')] || formatClinicalTermLabel(source, '未知来源')
}

function detailText(item: Citation): string {
  if (item.summary) return formatClinicalText(item.summary, '')
  const ref = citationId(item)
  if (!props.context) return ''
  if (ref === 'V' || ref === 'V1') {
    const v = props.context.v
    if (!v) return ''
    return `HR ${formatRange(v.hr?.min, v.hr?.max)}，MAP ${formatRange(v.map?.min, v.map?.max)}，SpO2 ${formatRange(v.spo2?.min, v.spo2?.max)}`
  }
  if (ref.startsWith('L')) {
    const lab = props.context.labs?.find((l: any) => `L${l.id}` === ref)
    return lab ? formatClinicalText(`${lab.name}: ${lab.prev} -> ${lab.curr}${lab.unit || ''} ${lab.flag || ''}`, '') : ''
  }
  if (ref.startsWith('D')) {
    const drug = props.context.drugs?.find((d: any) => `D${d.id}` === ref)
    return drug ? formatClinicalText(`${drug.time_hm} ${drug.action} ${drug.name} ${drug.dose_after || ''}`, '') : ''
  }
  if (ref.startsWith('A')) {
    const alert = props.context.alerts?.find((a: any) => `A${a.id}` === ref)
    return alert ? formatClinicalText(`${alert.type} ${alert.severity} x${alert.count}`, '') : ''
  }
  if (ref === 'AS1') {
    const s = props.context.scores
    return s ? `GCS ${s.gcs}，SOFA ${s.sofa}，APACHE ${s.apache}` : ''
  }
  if (ref === 'VT0') {
    const v = props.context.vent
    if (!v) return ''
    const peep = Number(v.peep) ? `，呼气末正压=${v.peep}` : ''
    return `${v.mode}，吸氧浓度=${v.fio2}${peep}，氧合指数=${v.pf_ratio ?? '未提供'}`
  }
  return ''
}

function formatRange(min: any, max: any) {
  if (min == null || max == null) return '未提供'
  return min === max ? String(min) : `${min}-${max}`
}
</script>

<style scoped>
.citation-panel {
  font-size: 12px;
}

.cp-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.cp-title {
  font-weight: 700;
  font-size: 14px;
}

.cp-count {
  color: #98a2b3;
  font-size: 11px;
}

.cp-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.cp-card {
  padding: 9px 10px;
  background: #f8fafc;
  border: 1px solid #edf1f7;
  border-radius: 8px;
}

.cp-card-ref {
  font-weight: 700;
  color: #1677ff;
  margin-bottom: 3px;
}

.cp-card-source {
  color: #344054;
  font-weight: 600;
}

.cp-card-time {
  color: #98a2b3;
  margin-top: 2px;
}

.cp-card-detail {
  margin-top: 6px;
  color: #667085;
  line-height: 1.55;
  border-top: 1px dashed #edf1f7;
  padding-top: 6px;
}

.cp-empty {
  text-align: center;
  color: #98a2b3;
  padding: 40px 0;
}
</style>
