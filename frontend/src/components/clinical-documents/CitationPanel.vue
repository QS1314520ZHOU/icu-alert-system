<template>
  <div class="citation-panel">
    <div class="cp-header">
      <span class="cp-title">🔗 引用溯源</span>
      <span class="cp-count">{{ citations.length }} 条</span>
    </div>
    <div v-if="citations.length" class="cp-list">
      <div
        v-for="c in citations"
        :key="c.ref"
        class="cp-card"
      >
        <div class="cp-card-ref">[{{ c.ref }}]</div>
        <div class="cp-card-source">{{ c.source }}</div>
        <div v-if="sourceDetail(c)" class="cp-card-detail">{{ sourceDetail(c) }}</div>
      </div>
    </div>
    <div v-else class="cp-empty">
      暂无引用信息
    </div>
  </div>
</template>

<script setup lang="ts">
import type { Citation } from '../../api/clinicalDocuments'

const props = defineProps<{
  citations: Citation[]
  context: any
}>()

function sourceDetail(c: Citation): string {
  if (!props.context) return ''
  const ref = c.ref
  if (ref === 'V') {
    const v = props.context.v
    if (!v) return ''
    return `HR ${v.hr?.min}~${v.hr?.max}, MAP ${v.map?.min}~${v.map?.max}, SpO2 ${v.spo2?.min}~${v.spo2?.max}`
  }
  if (ref.startsWith('L')) {
    const id = parseInt(ref.slice(1))
    const lab = props.context.labs?.find((l: any) => l.id === id)
    return lab ? `${lab.name}: ${lab.prev}→${lab.curr}${lab.unit} ${lab.flag}` : ''
  }
  if (ref.startsWith('D')) {
    const id = parseInt(ref.slice(1))
    const drug = props.context.drugs?.find((d: any) => d.id === id)
    return drug ? `${drug.time_hm} ${drug.action} ${drug.name} ${drug.dose_after || ''}` : ''
  }
  if (ref.startsWith('A')) {
    const id = parseInt(ref.slice(1))
    const alert = props.context.alerts?.find((a: any) => a.id === id)
    return alert ? `${alert.type} ${alert.severity} ×${alert.count}` : ''
  }
  if (ref === 'AS1') {
    const s = props.context.scores
    return s ? `GCS ${s.gcs} SOFA ${s.sofa} APACHE ${s.apache}` : ''
  }
  if (ref === 'VT0') {
    const v = props.context.vent
    return v ? `${v.mode} FiO2=${v.fio2} PEEP=${v.peep}` : ''
  }
  return ''
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
  font-weight: 600;
  font-size: 14px;
}
.cp-count {
  font-size: 11px;
  color: #8c8c8c;
}
.cp-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.cp-card {
  padding: 8px 10px;
  background: #fafafa;
  border: 1px solid #f0f0f0;
  border-radius: 6px;
  transition: border-color 0.2s;
}
.cp-card:hover {
  border-color: #1677ff;
}
.cp-card-ref {
  font-weight: 600;
  color: #1677ff;
  margin-bottom: 2px;
}
.cp-card-source {
  color: #595959;
  font-size: 12px;
}
.cp-card-detail {
  margin-top: 4px;
  color: #8c8c8c;
  font-size: 11px;
  line-height: 1.5;
  border-top: 1px dashed #f0f0f0;
  padding-top: 4px;
}
.cp-empty {
  text-align: center;
  color: #bfbfbf;
  padding: 40px 0;
}

/* ================= Dark Theme Overrides ================= */
:global(.theme-dark) .cp-count {
  color: #7f93ab;
}
:global(.theme-dark) .cp-card {
  background: #091827;
  border-color: rgba(125, 167, 214, 0.14);
}
:global(.theme-dark) .cp-card:hover {
  border-color: #22d3ee;
}
:global(.theme-dark) .cp-card-ref {
  color: #22d3ee;
}
:global(.theme-dark) .cp-card-source {
  color: #d9e6f3;
}
:global(.theme-dark) .cp-card-detail {
  color: #7f93ab;
  border-top-color: rgba(125, 167, 214, 0.14);
}
:global(.theme-dark) .cp-empty {
  color: #586b82;
}
</style>
