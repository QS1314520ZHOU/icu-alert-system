<template>
  <div class="detail-container">
    <a-page-header
      :title="displayName"
      :sub-title="displaySubTitle"
      @back="backToList"
      style="background: #112240; border-radius: 8px; margin-bottom: 16px;"
    />
    <div class="detail-content">
      <a-card title="基本信息" :bordered="false" class="info-card">
        <p>诊断: {{ displayDiagnosis }}</p>
        <p>入院时间: {{ displayAdmissionTime }}</p>
        <p>HIS编号: {{ displayHisPid }}</p>
      </a-card>
      <a-card title="生命体征" :bordered="false" class="info-card vitals-card">
        <div v-if="vitals?.source" class="vitals-grid">
          <div class="v-item">
            <span class="v-label">来源</span>
            <span class="v-value">{{ vitalsSourceText }}</span>
          </div>
          <div class="v-item">
            <span class="v-label">时间</span>
            <span class="v-value">{{ fmtTime(vitals.time) || '—' }}</span>
          </div>
          <div class="v-item">
            <span class="v-label">HR</span>
            <span class="v-value">{{ vitals.hr ?? '—' }}</span>
          </div>
          <div class="v-item">
            <span class="v-label">SpO₂</span>
            <span class="v-value">{{ vitals.spo2 != null ? vitals.spo2 + '%' : '—' }}</span>
          </div>
          <div class="v-item">
            <span class="v-label">RR</span>
            <span class="v-value">{{ vitals.rr ?? '—' }}</span>
          </div>
          <div class="v-item">
            <span class="v-label">BP</span>
            <span class="v-value">{{ fmtBP(vitals) }}</span>
          </div>
          <div class="v-item">
            <span class="v-label">T</span>
            <span class="v-value">{{ fmtTemp(vitals.temp) }}</span>
          </div>
        </div>
        <div v-else class="vitals-empty">暂无监护数据</div>
      </a-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getPatientDetail, getPatientVitals } from '../api'

const route = useRoute()
const router = useRouter()
const patient = ref<any>(null)
const vitals = ref<any>(null)

const displayName = computed(() =>
  patient.value?.name || patient.value?.hisName || '加载中...'
)
const displaySubTitle = computed(() => {
  const bed = patient.value?.hisBed || patient.value?.bed || '--'
  const gender = patient.value?.genderText || patient.value?.hisSex || ''
  const age = patient.value?.age || patient.value?.hisAge || ''
  return `${bed}床 | ${gender} ${age}`.trim()
})
const displayDiagnosis = computed(() =>
  patient.value?.clinicalDiagnosis ||
  patient.value?.admissionDiagnosis ||
  patient.value?.hisDiagnose ||
  '暂无'
)
const displayAdmissionTime = computed(() =>
  patient.value?.icuAdmissionTime ||
  patient.value?.admissionTime ||
  '未知'
)
const displayHisPid = computed(() =>
  patient.value?.hisPid || patient.value?.hisPID || '无'
)

const vitalsSourceText = computed(() => {
  if (!vitals.value?.source) return ''
  if (vitals.value.source === 'monitor') return '监护仪'
  if (vitals.value.source === 'nurse_manual') return '护士录入'
  return '未知'
})

function fmtBP(v: any) {
  const s = v?.nibp_sys, d = v?.nibp_dia
  return s != null || d != null ? `${s ?? '—'}/${d ?? '—'}` : '—'
}
function fmtTemp(v: any) {
  if (v == null) return '—'
  const n = Number(v)
  return isNaN(n) ? '—' : n.toFixed(1)
}
function fmtTime(t: any) {
  if (!t) return ''
  try {
    const d = new Date(t)
    const yyyy = d.getFullYear()
    const mm = String(d.getMonth() + 1).padStart(2, '0')
    const dd = String(d.getDate()).padStart(2, '0')
    const hh = String(d.getHours()).padStart(2, '0')
    const mi = String(d.getMinutes()).padStart(2, '0')
    return `${yyyy}-${mm}-${dd} ${hh}:${mi}`
  } catch { return '' }
}

function backToList() {
  router.push({ path: '/', query: route.query })
}

onMounted(async () => {
  const patientId = route.params.id as string
  try {
    const res = await getPatientDetail(patientId)
    patient.value = res.data.patient || null
  } catch (e) {
    console.error('加载患者失败', e)
  }

  try {
    const vRes = await getPatientVitals(patientId)
    vitals.value = vRes.data.vitals || null
  } catch (e) {
    console.error('加载生命体征失败', e)
  }
})
</script>

<style scoped>
.detail-container {
  max-width: 1400px;
  margin: 0 auto;
}
.info-card {
  background: #112240;
  border: 1px solid #1e3a5f;
  border-radius: 8px;
  margin-bottom: 16px;
}
.vitals-card :deep(.ant-card-body) {
  padding-top: 8px;
}
.vitals-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 10px;
}
.v-item {
  background: #0d1f3a;
  border: 1px solid #1b2d4d;
  border-radius: 6px;
  padding: 10px 12px;
}
.v-label {
  display: block;
  font-size: 11px;
  color: #7aa2d6;
  margin-bottom: 4px;
}
.v-value {
  font-size: 16px;
  font-weight: 700;
  color: #e6f0ff;
  font-family: 'JetBrains Mono', 'Consolas', monospace;
}
.vitals-empty {
  color: #6b7280;
  font-size: 12px;
  padding: 10px 0;
}
</style>
