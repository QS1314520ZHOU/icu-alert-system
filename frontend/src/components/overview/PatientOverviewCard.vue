<template>
  <article
    ref="cardEl"
    :class="['card', `card--${patient.alertLevel || 'none'}`, { 'card--flash': patient.alertFlash }]"
    @mouseenter="handleCardIntent"
    @focusin="handleCardIntent"
    @click="emit('select', patient._id)"
  >
    <section class="sec-top">
      <header class="card-header">
        <div class="patient-identity">
          <span class="bed-no">{{ patient.hisBed }}</span>
          <div class="identity-copy">
            <div class="monitor-line">
              <span class="monitor-label">重症监护</span>
              <span class="monitor-sep"></span>
              <span class="monitor-code">床位 {{ patient.hisBed || '--' }}</span>
            </div>
            <div class="name-row">
              <h2 class="patient-name">{{ patient.name || '—' }}</h2>
              <span class="patient-meta">{{ genderLabel }}/{{ patient.age || '—' }}</span>
            </div>
            <p class="diag-text" :title="patient.clinicalDiagnosis">{{ shortDiag(patient.clinicalDiagnosis) || '无初步诊断' }}</p>
            <div class="monitor-meta-row">
              <span class="monitor-meta-chip">{{ monitorSourceText }}</span>
              <span class="monitor-meta-chip">{{ monitorUpdatedText }}</span>
              <span v-if="patient.hasRescueRisk" class="monitor-meta-chip monitor-meta-chip--rescue">抢救期风险</span>
            </div>
          </div>
        </div>
        <div :class="['status-badge', `status-badge--${patient.alertLevel || 'none'}`]">
          <strong>{{ alertStatus }}</strong>
        </div>
      </header>
      <div class="patient-tags">
        <span v-if="bedcard?.identity?.allergies || patient.allergies" class="allergy-tag">
          过敏：{{ bedcard?.identity?.allergies || patient.allergies }}
        </span>
      </div>
    </section>

    <section class="sec-vitals">
      <div class="section-head">
        <span class="section-title">生命体征</span>
        <span class="section-desc">最近一次监测</span>
      </div>
      <div class="vital-grid">
        <div v-for="v in vitalsData" :key="v.key" :class="['vital-item', `vital-item--${v.key}`, v.colorClass]">
          <span class="v-label">{{ v.label }}</span>
          <span class="v-val">{{ v.value }}<small v-if="v.unit && v.value !== '--'">{{ v.unit }}</small></span>
        </div>
      </div>
    </section>

    <section class="sec-risk-fingerprint">
      <div class="section-head">
        <span class="section-title">器官风险指纹</span>
        <span class="section-desc">6 轴扫描</span>
      </div>
      <div class="risk-fingerprint">
        <OrganRiskRadar :scores="organRadarScores" :size="104" />
        <div class="risk-fingerprint__chips">
          <span
            v-for="chip in organRiskChips"
            :key="chip.key"
            :class="['risk-fingerprint__chip', `is-${chip.severity}`]"
          >
            {{ chip.label }} · {{ chip.text }}
          </span>
        </div>
      </div>
    </section>

    <section
      v-if="summaryCard && isRescueSummary(summaryCard)"
      class="sec-rescue-spotlight"
    >
      <div class="rescue-spotlight-head">
        <span class="rescue-spotlight-tag">抢救期风险卡</span>
        <span :class="['rescue-spotlight-sev', `rescue-spotlight-sev--${severityTone(summaryCard.severity)}`]">{{ severityLabel(summaryCard.severity) }}</span>
      </div>
      <div class="rescue-spotlight-title">{{ summaryRescueTitle(summaryCard) }}</div>
      <div v-if="summaryCard.summary" class="rescue-spotlight-main">{{ summaryCard.summary }}</div>
      <div v-if="summaryEvidence(summaryCard).length" class="summary-chip-row summary-chip-row--rescue">
        <span v-for="(ev, idx) in summaryEvidence(summaryCard)" :key="`spot-ev-${idx}`" class="summary-chip summary-chip--rescue">{{ ev }}</span>
      </div>
      <div v-if="summarySnapshotRows(summaryCard).length" class="summary-mini-snapshot">
        <span v-for="(chip, idx) in summarySnapshotRows(summaryCard)" :key="`spot-chip-${idx}`" class="summary-mini-chip">
          <span class="summary-mini-chip-label">{{ chip.label }}</span>
          <strong class="summary-mini-chip-value">{{ chip.value }}</strong>
        </span>
      </div>
      <div v-if="summaryCard.suggestion" class="rescue-spotlight-suggestion">{{ summaryCard.suggestion }}</div>
    </section>

    <section class="sec-logistics" v-if="bedcard?.devices?.length || bedcard?.tubes?.length">
      <div class="section-head">
        <span class="section-title">设备与管路</span>
        <span v-if="bedcard?.tubes?.length" class="section-desc">{{ bedcard.tubes.length }} 项留置</span>
      </div>
      <div v-if="bedcard?.devices?.length" class="info-block">
        <span class="info-label">设备</span>
        <div class="device-list">
          <span v-for="(dev, idx) in bedcard.devices.slice(0, 2)" :key="idx" class="device-tag">
            <i class="dev-dot"></i>{{ dev.name }}
          </span>
        </div>
      </div>
      <div v-if="bedcard?.tubes?.length" class="info-block">
        <span class="info-label">管路</span>
        <div :class="['tube-list', { 'tube-list--folded': !showAllTubes }]">
          <span v-for="(t, idx) in formattedTubesList" :key="idx" :class="['tube-item', tubeClass(t.dwellDays)]">
            {{ t.name }} D{{ t.dwellDays }}
          </span>
        </div>
        <button v-if="bedcard.tubes.length > 4" type="button" class="tube-toggle" @click.stop="showAllTubes = !showAllTubes">
          {{ showAllTubes ? '收起' : `展开全部（${bedcard.tubes.length}）` }}
        </button>
      </div>
    </section>

    <section class="sec-alerts" v-if="alertNotes.length || bedcard?.notes?.length || bundleProgress">
      <div class="section-head">
        <span class="section-title">护理提醒</span>
      </div>
      <div class="alert-line" v-if="bundleProgress">
        <span class="alert-dot alert-dot--yellow"></span>
        <span class="alert-text">防控清单完成度 {{ bundleProgress }}</span>
      </div>
      <div v-for="(note, idx) in alertNotes" :key="`${note.rule_id || note.title || 'note'}-${idx}`" :class="['alert-card', `alert-card--${note.severity || 'high'}`]">
        <div class="alert-card-top">
          <div class="alert-card-title-row">
            <span :class="['alert-dot', `alert-dot--${note.severity || 'red'}`]"></span>
            <span class="alert-card-title">{{ note.title }}</span>
          </div>
          <span class="alert-card-time">{{ noteTimeText(note.created_at) }}</span>
        </div>
        <div :class="['alert-card-summary', { 'alert-card-summary--rescue': isRescueSummary(note) }]">{{ note.summary }}</div>
        <div v-if="summaryEvidence(note).length" :class="['summary-chip-row', 'summary-chip-row--inline', { 'summary-chip-row--rescue': isRescueSummary(note) }]">
          <span v-for="(ev, eIdx) in summaryEvidence(note)" :key="`${idx}-${eIdx}`" :class="['summary-chip', { 'summary-chip--rescue': isRescueSummary(note) }]">
            {{ ev }}
          </span>
        </div>
        <div v-if="summarySnapshotRows(note).length" class="summary-mini-snapshot">
          <span v-for="(chip, chipIdx) in summarySnapshotRows(note)" :key="`note-shot-${idx}-${chipIdx}`" class="summary-mini-chip">
            <span class="summary-mini-chip-label">{{ chip.label }}</span>
            <strong class="summary-mini-chip-value">{{ chip.value }}</strong>
          </span>
        </div>
        <div v-if="note.suggestion" :class="['alert-card-suggestion', { 'alert-card-suggestion--rescue': isRescueSummary(note) }]">{{ note.suggestion }}</div>
      </div>
      <div v-if="!alertNotes.length" v-for="(note, idx) in fallbackNotes" :key="idx" class="alert-line">
        <span class="alert-dot alert-dot--red"></span>
        <span class="alert-text">{{ note }}</span>
      </div>
    </section>

    <section
      v-if="summaryCard && (summaryCard.summary || summaryChain(summaryCard) || summaryGroups(summaryCard).length)"
      class="sec-summary"
    >
      <div class="section-head">
        <span class="section-title">{{ isRescueSummary(summaryCard) ? '抢救期风险卡' : '综合预警卡' }}</span>
        <span class="section-desc">{{ noteTimeText(summaryCard.created_at) }}</span>
      </div>
      <div :class="['summary-top', { 'summary-top--rescue': isRescueSummary(summaryCard) }]">
        <div v-if="isRescueSummary(summaryCard)" class="summary-rescue-head">
          <span class="summary-rescue-tag">抢救期风险卡</span>
          <span :class="['summary-rescue-sev', `summary-rescue-sev--${severityTone(summaryCard.severity)}`]">{{ severityLabel(summaryCard.severity) }}</span>
        </div>
        <div class="summary-title-row">
          <span :class="['alert-dot', `alert-dot--${summaryCard.severity || 'red'}`]"></span>
          <span class="summary-title">{{ isRescueSummary(summaryCard) ? summaryRescueTitle(summaryCard) : (summaryCard.title || '综合预警') }}</span>
        </div>
      </div>
      <div v-if="summaryCard.summary" :class="['summary-main-wrap', { 'summary-main-wrap--rescue': isRescueSummary(summaryCard) }]">
        <div class="summary-block-label">{{ isRescueSummary(summaryCard) ? '当前判断' : '摘要' }}</div>
        <div :class="['summary-main', { 'summary-main--rescue': isRescueSummary(summaryCard) }]">{{ summaryCard.summary }}</div>
      </div>
      <div v-if="summaryChain(summaryCard)" class="summary-chain">
        <div class="summary-chain-head">
          <span class="summary-chain-tag">{{ isRescueSummary(summaryCard) ? '病理生理链' : '临床链' }}</span>
          <span class="summary-chain-code">{{ chainLabel(summaryChain(summaryCard)?.chain_type) }}</span>
        </div>
        <div class="summary-chain-text">{{ summaryChain(summaryCard)?.summary }}</div>
      </div>
      <div v-if="summaryEvidence(summaryCard).length" :class="['summary-chip-row', { 'summary-chip-row--rescue': isRescueSummary(summaryCard) }]">
        <div class="summary-block-label">{{ isRescueSummary(summaryCard) ? '主要依据' : '证据' }}</div>
        <span v-for="(ev, idx) in summaryEvidence(summaryCard)" :key="`sum-ev-${idx}`" :class="['summary-chip', { 'summary-chip--rescue': isRescueSummary(summaryCard) }]">
          {{ ev }}
        </span>
      </div>
      <div v-if="summarySnapshot(summaryCard)" class="summary-snapshot">
        <div class="summary-snapshot-head">
          <span class="summary-chain-tag">{{ isRescueSummary(summaryCard) ? '风险快照' : '微型快照' }}</span>
          <span class="summary-chain-code">{{ snapshotTime(summaryCard) }}</span>
        </div>
        <div v-if="summaryVitals(summaryCard).length" class="summary-snapshot-row">
          <span class="summary-snapshot-label">生命体征</span>
          <div class="summary-snapshot-chip-row">
            <span v-for="(chip, idx) in summaryVitals(summaryCard)" :key="`sum-vital-${idx}`" class="summary-mini-chip">
              <span class="summary-mini-chip-label">{{ chip.label }}</span>
              <strong class="summary-mini-chip-value">{{ chip.value }}</strong>
            </span>
          </div>
        </div>
        <div v-if="summaryLabs(summaryCard).length" class="summary-snapshot-row">
          <span class="summary-snapshot-label">关键检验</span>
          <div class="summary-snapshot-chip-row">
            <span v-for="(chip, idx) in summaryLabs(summaryCard)" :key="`sum-lab-${idx}`" class="summary-mini-chip summary-mini-chip--lab">
              <span class="summary-mini-chip-label">{{ chip.label }}</span>
              <strong class="summary-mini-chip-value">{{ chip.value }}</strong>
            </span>
          </div>
        </div>
        <div v-if="summaryVaso(summaryCard).length" class="summary-snapshot-row">
          <span class="summary-snapshot-label">血管活性药</span>
          <div class="summary-snapshot-badge-row">
            <span v-for="(badge, idx) in summaryVaso(summaryCard)" :key="`sum-vaso-${idx}`" class="summary-vaso-badge">
              <span class="summary-vaso-name">{{ badge.drug }}</span>
              <span class="summary-vaso-dose">{{ badge.dose }}</span>
            </span>
          </div>
        </div>
      </div>
      <div v-if="summaryGroups(summaryCard).length" class="summary-chip-row">
        <span
          v-for="(group, idx) in summaryGroups(summaryCard)"
          :key="`sum-group-${idx}`"
          :class="['summary-chip', 'summary-chip--group', `summary-chip--${severityTone(group.severity)}`]"
        >
          {{ groupLabel(group.group) }} · {{ group.count || 0 }}
        </span>
      </div>
      <div v-if="summaryCard.suggestion" :class="['summary-suggestion', { 'summary-suggestion--rescue': isRescueSummary(summaryCard) }]">
        <div class="summary-block-label">{{ isRescueSummary(summaryCard) ? '处置建议' : '建议' }}</div>
        {{ summaryCard.suggestion }}
      </div>
    </section>

    <aside
      v-if="summaryCard && (summaryCard.summary || summarySnapshot(summaryCard) || summaryEvidence(summaryCard).length)"
      :class="['hover-drawer', { 'hover-drawer--rescue': isRescueSummary(summaryCard) }]"
    >
      <div class="hover-drawer-head">
        <span class="hover-drawer-tag">{{ isRescueSummary(summaryCard) ? '抢救期风险卡' : '综合预警摘要' }}</span>
        <span :class="['hover-drawer-sev', `hover-drawer-sev--${severityTone(summaryCard.severity)}`]">{{ severityLabel(summaryCard.severity) }}</span>
      </div>
      <div class="hover-drawer-title">{{ summaryRescueTitle(summaryCard) }}</div>
      <div v-if="summaryCard.summary" class="hover-drawer-block hover-drawer-block--summary">
        <div class="hover-drawer-label">当前判断</div>
        <div class="hover-drawer-main">{{ summaryCard.summary }}</div>
      </div>
      <div v-if="summaryChain(summaryCard)" class="hover-drawer-block hover-drawer-block--chain">
        <div class="summary-chain-head">
          <span class="summary-chain-tag">病理生理链</span>
          <span class="summary-chain-code">{{ chainLabel(summaryChain(summaryCard)?.chain_type) }}</span>
        </div>
        <div class="summary-chain-text">{{ summaryChain(summaryCard)?.summary }}</div>
      </div>
      <div v-if="summaryEvidence(summaryCard).length" class="summary-chip-row summary-chip-row--rescue">
        <div class="hover-drawer-label">主要依据</div>
        <span v-for="(ev, idx) in summaryEvidence(summaryCard)" :key="`hover-ev-${idx}`" class="summary-chip summary-chip--rescue">{{ ev }}</span>
      </div>
      <div v-if="summarySnapshotRows(summaryCard).length" class="hover-drawer-block hover-drawer-block--snapshot">
        <div class="hover-drawer-label">风险快照</div>
        <div class="summary-mini-snapshot">
        <span v-for="(chip, idx) in summarySnapshotRows(summaryCard)" :key="`hover-shot-${idx}`" class="summary-mini-chip">
          <span class="summary-mini-chip-label">{{ chip.label }}</span>
          <strong class="summary-mini-chip-value">{{ chip.value }}</strong>
        </span>
        </div>
      </div>
      <div v-if="summaryGroups(summaryCard).length" class="summary-chip-row">
        <span
          v-for="(group, idx) in summaryGroups(summaryCard)"
          :key="`hover-group-${idx}`"
          :class="['summary-chip', 'summary-chip--group', `summary-chip--${severityTone(group.severity)}`]"
        >
          {{ groupLabel(group.group) }} · {{ group.count || 0 }}
        </span>
      </div>
      <div v-if="summaryCard.suggestion" class="hover-drawer-suggestion">
        <div class="hover-drawer-label">处置建议</div>
        {{ summaryCard.suggestion }}
      </div>
    </aside>

    <section class="sec-footer">
      <div class="bundle-panel">
        <div class="bundle-head">
          <span class="footer-title">ABCDEF 防控清单</span>
          <span v-if="bundleProgress" class="bundle-score">{{ bundleProgress }}</span>
        </div>
        <div class="bundle-dots">
          <span
            v-for="light in bundleLights(patient)"
            :key="light.key"
            :class="['mini-dot', `mini--${light.state}`]"
            :title="`${light.name}：${light.statusText}`"
          >{{ light.key }}</span>
        </div>
      </div>
      <div class="footer-pills">
        <span
          v-if="patient.alertLevel && patient.alertLevel !== 'none'"
          :class="['pill', 'pill--severity', `pill--severity-${patient.alertLevel}`]"
        >{{ alertStatus }}</span>
        <span v-if="bedcard?.identity?.isolation" class="pill pill--iso">{{ bedcard.identity.isolation }}</span>
        <span v-if="patientDiet(patient)" class="pill pill--diet">{{ patientDiet(patient) }}</span>
      </div>
    </section>
  </article>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch, computed } from 'vue'
import { getPatientBedcard } from '../../api'
import OrganRiskRadar from '../common/OrganRiskRadar.vue'
import { formatAlertTypeLabel, formatCompositeChainLabel, formatCompositeGroupLabel, formatSeverityLabel } from '../../utils/displayLabels'
import {
  BODY_MAP_ORGAN_LABELS,
  BODY_MAP_ORGAN_ORDER,
  bodyMapSeverityText,
  organStateMapToScores,
  normalizeBodyMapSeverity,
} from '../../utils/bodyMap'

const BEDCARD_CACHE_TTL_MS = 60 * 1000
const BEDCARD_FAIL_COOLDOWN_MS = 45 * 1000
const BEDCARD_MAX_CONCURRENT = 2
const bedcardCache = new Map<string, { data: any; expiresAt: number }>()
const bedcardInFlight = new Map<string, Promise<any>>()
const bedcardFailCooldown = new Map<string, number>()
const bedcardRequestQueue: Array<() => void> = []
let bedcardActiveRequests = 0

const props = defineProps<{
  patient: any
}>()

const emit = defineEmits<{
  (e: 'select', id: string): void
}>()

const bedcard = ref<any>(null)
const showAllTubes = ref(false)
const cardEl = ref<HTMLElement | null>(null)
const shouldLoadBedcard = ref(false)
let cardObserver: IntersectionObserver | null = null
const genderLabel = computed(() => props.patient?.gender === 'Female' ? '女' : props.patient?.gender === 'Male' ? '男' : '—')
const alertStatus = computed(() => {
  const map: Record<string, string> = {
    critical: '危急',
    high: '高风险',
    warning: '预警',
    normal: '稳定',
    none: '待评估'
  }
  return map[props.patient?.alertLevel || 'none'] || '待评估'
})

const mergedVitals = computed(() => {
  const cardVitals = bedcard.value?.metrics?.vitals && typeof bedcard.value.metrics.vitals === 'object'
    ? bedcard.value.metrics.vitals
    : {}
  const patientVitals = props.patient?.vitals && typeof props.patient.vitals === 'object'
    ? props.patient.vitals
    : {}
  return {
    ...patientVitals,
    ...Object.fromEntries(Object.entries(cardVitals).filter(([, value]) => value != null && value !== '')),
  }
})

const vitalsData = computed(() => {
  const v = mergedVitals.value || {}
  const sbp = pickVital(v.sbp, v.ibp_sys, v.nibp_sys)
  const dbp = pickVital(v.dbp, v.ibp_dia, v.nibp_dia)
  const hr = pickVital(v.hr)
  const spo2 = pickVital(v.spo2)
  const temperature = pickVital(v.t, v.temp)
  return [
    { key: 'hr', label: 'HR', value: formatVitalNumber(hr, 0), colorClass: vitalClass('hr', hr) },
    { key: 'bp', label: 'BP', value: sbp != null ? `${formatVitalNumber(sbp, 0)}/${dbp != null ? formatVitalNumber(dbp, 0) : '--'}` : '--', colorClass: vitalClass('bp', sbp) },
    { key: 'spo2', label: 'SpO₂', value: formatVitalNumber(spo2, 0), unit: '%', colorClass: vitalClass('spo2', spo2) },
    { key: 'temp', label: 'T', value: temp(temperature), unit: '℃', colorClass: vitalClass('t', temperature) }
  ]
})

const formattedTubesList = computed(() => {
  return bedcard.value?.tubes || []
})

const organRadarScores = computed(() => organStateMapToScores(props.patient?.organMap || {}))
const organRiskChips = computed(() =>
  BODY_MAP_ORGAN_ORDER.map((key) => {
    const severity = normalizeBodyMapSeverity(props.patient?.organMap?.[key])
    return {
      key,
      label: BODY_MAP_ORGAN_LABELS[key],
      severity,
      text: bodyMapSeverityText(severity),
    }
  }).filter((item) => item.severity !== 'normal' || organRadarScores.value.every((score) => score === 0))
    .slice(0, 4)
)

const alertNotes = computed(() => {
  const list = Array.isArray(bedcard.value?.alert_notes) ? bedcard.value.alert_notes : []
  return list.slice(0, 2).map((item: any) => normalizeAlertTextPayload(item))
})

const fallbackNotes = computed(() =>
  (Array.isArray(bedcard.value?.notes) ? bedcard.value.notes : []).slice(0, 2).map((item: any) => humanizeClinicalText(item))
)

const summaryCard = computed(() => normalizeAlertTextPayload(bedcard.value?.alert_summary_card || null))

const bundleProgress = computed(() => {
  const lights = (bundleLights(props.patient) || []).filter(l => l.state !== 'unknown')
  if (!lights.length) return ''
  const done = lights.filter(l => l.state === 'green').length
  return `${done}/${lights.length}`
})
const monitorSourceText = computed(() => {
  const source = String(mergedVitals.value?.source || '').trim().toLowerCase()
  if (source === 'monitor') return '监护仪'
  if (source === 'nurse_manual') return '护士录入'
  if (source === 'alert_snapshot') return '告警快照'
  if (source === 'bedside') return '床旁记录'
  if (source === 'bedside_text') return '床旁记录'
  if (source) return humanizeClinicalText(source)
  return '监护来源未标注'
})
const monitorUpdatedText = computed(() => {
  const text = noteTimeText(mergedVitals.value?.time)
  return text ? `更新 ${text}` : '时间未知'
})

function getCacheKey() {
  return props.patient?._id ? String(props.patient._id) : ''
}

function tryUseCachedBedcard(cacheKey: string, now = Date.now()) {
  const cached = bedcardCache.get(cacheKey)
  if (!cached) return false
  if (cached.expiresAt <= now) {
    bedcardCache.delete(cacheKey)
    return false
  }
  bedcard.value = cached.data
  return true
}

function primeBedcardCache(cacheKey: string, data: any) {
  bedcardCache.set(cacheKey, {
    data,
    expiresAt: Date.now() + BEDCARD_CACHE_TTL_MS,
  })
}

function dequeueBedcardRequest() {
  if (bedcardActiveRequests >= BEDCARD_MAX_CONCURRENT) return
  const next = bedcardRequestQueue.shift()
  if (next) next()
}

function runBedcardRequest<T>(task: () => Promise<T>) {
  return new Promise<T>((resolve, reject) => {
    const execute = () => {
      bedcardActiveRequests += 1
      task()
        .then(resolve)
        .catch(reject)
        .finally(() => {
          bedcardActiveRequests = Math.max(0, bedcardActiveRequests - 1)
          dequeueBedcardRequest()
        })
    }
    if (bedcardActiveRequests < BEDCARD_MAX_CONCURRENT) {
      execute()
    } else {
      bedcardRequestQueue.push(execute)
    }
  })
}

async function loadBedcard() {
  if (!props.patient?._id) return
  const cacheKey = getCacheKey()
  const now = Date.now()
  if (!cacheKey) return
  if (tryUseCachedBedcard(cacheKey, now)) {
    return
  }
  const cooldownUntil = bedcardFailCooldown.get(cacheKey) || 0
  if (cooldownUntil > now) return
  const existing = bedcardInFlight.get(cacheKey)
  if (existing) {
    try {
      const data = await existing
      if (data) bedcard.value = data
    } catch {
      // noop: 失败由创建请求处处理
    }
    return
  }
  const request = runBedcardRequest(async () => {
    const res = await getPatientBedcard(props.patient._id, 5000)
    if (res.data?.code === 0) {
      const data = res.data.data || null
      primeBedcardCache(cacheKey, data)
      bedcardFailCooldown.delete(cacheKey)
      return data
    }
    throw new Error('bedcard response invalid')
  })
  bedcardInFlight.set(cacheKey, request)
  try {
    const data = await request
    bedcard.value = data
  } catch {
    bedcardFailCooldown.set(cacheKey, now + BEDCARD_FAIL_COOLDOWN_MS)
  } finally {
    bedcardInFlight.delete(cacheKey)
  }
}

function handleCardIntent() {
  if (shouldLoadBedcard.value) return
  shouldLoadBedcard.value = true
  void loadBedcard()
}

onMounted(() => {
  if (!cardEl.value || typeof IntersectionObserver === 'undefined') {
    handleCardIntent()
    return
  }
  cardObserver = new IntersectionObserver((entries) => {
    if (!entries.some((entry) => entry.isIntersecting)) return
    handleCardIntent()
    cardObserver?.disconnect()
    cardObserver = null
  }, { rootMargin: '180px 0px', threshold: 0.05 })
  cardObserver.observe(cardEl.value)
})

onBeforeUnmount(() => {
  if (cardObserver) {
    cardObserver.disconnect()
    cardObserver = null
  }
})

watch(() => props.patient?._id, () => {
  bedcard.value = null
  showAllTubes.value = false
  shouldLoadBedcard.value = false
  if (cardObserver) {
    cardObserver.disconnect()
    cardObserver = null
  }
  if (!cardEl.value || typeof IntersectionObserver === 'undefined') {
    handleCardIntent()
    return
  }
  cardObserver = new IntersectionObserver((entries) => {
    if (!entries.some((entry) => entry.isIntersecting)) return
    handleCardIntent()
    cardObserver?.disconnect()
    cardObserver = null
  }, { rootMargin: '180px 0px', threshold: 0.05 })
  cardObserver.observe(cardEl.value)
})

function vitalClass(type: string, val: any) {
  if (val == null) return ''
  const n = parseFloat(val)
  if (isNaN(n)) return ''
  
  if (type === 'hr') {
    if (n >= 120 || n <= 40) return 'vital--red'
    if (n >= 100 || n <= 50) return 'vital--orange'
  }
  if (type === 'bp') {
    if (n >= 180 || n <= 80) return 'vital--red'
    if (n >= 140 || n <= 90) return 'vital--orange'
  }
  if (type === 'spo2') {
    if (n <= 85) return 'vital--red'
    if (n <= 90) return 'vital--orange'
  }
  if (type === 't') {
    if (n >= 39 || n <= 35) return 'vital--red'
    if (n >= 38 || n <= 36) return 'vital--orange'
  }
  return ''
}

function tubeClass(days: any) {
  const d = parseInt(days)
  if (isNaN(d)) return ''
  if (d >= 14) return 'tube--red'
  if (d >= 7) return 'tube--orange'
  return ''
}

function humanizeCodeToken(value: any) {
  const raw = String(value || '').trim()
  if (!raw) return ''
  const normalized = raw.toLowerCase()
  const sourceMap: Record<string, string> = {
    monitor: '监护仪',
    nurse_manual: '护士录入',
    alert_snapshot: '告警快照',
    bedside: '床旁记录',
    bedside_text: '床旁记录',
    score: '评分记录',
  }
  if (sourceMap[normalized]) return sourceMap[normalized]
  return formatAlertTypeLabel(normalized)
}

function humanizeClinicalText(value: any) {
  const raw = String(value || '').trim()
  if (!raw) return ''
  return raw.replace(/\b[a-z]+(?:_[a-z0-9]+)+\b/gi, (token) => humanizeCodeToken(token))
}

function normalizeAlertTextPayload<T>(payload: T): T {
  if (!payload || typeof payload !== 'object') return payload
  const row: any = { ...(payload as any) }
  if (row.title != null) row.title = humanizeClinicalText(row.title)
  if (row.summary != null) row.summary = humanizeClinicalText(row.summary)
  if (row.suggestion != null) row.suggestion = humanizeClinicalText(row.suggestion)
  if (row.rule_id != null) row.rule_id = humanizeClinicalText(row.rule_id)
  if (row.alert_type != null) row.alert_type = humanizeClinicalText(row.alert_type)
  if (row.source != null) row.source = humanizeClinicalText(row.source)
  if (Array.isArray(row.evidence)) {
    row.evidence = row.evidence.map((item: any) => humanizeClinicalText(item))
  }
  return row as T
}

function summaryChain(card: any) {
  const chain = card?.clinical_chain
  return chain && typeof chain === 'object' ? chain : null
}

function summaryGroups(card: any) {
  const rows = card?.aggregated_groups
  return Array.isArray(rows) ? rows.filter((x: any) => x && typeof x === 'object').slice(0, 3) : []
}

function summaryEvidence(card: any) {
  return Array.isArray(card?.evidence)
    ? card.evidence.map((x: any) => humanizeClinicalText(x)).filter((x: any) => String(x || '').trim()).slice(0, 3)
    : []
}

function summarySnapshot(card: any) {
  const ctx = card?.context_snapshot
  return ctx && typeof ctx === 'object' ? ctx : null
}

function postExtubationSnapshot(card: any) {
  const row = card?.post_extubation_snapshot
  return row && typeof row === 'object' ? row : null
}

function snapshotValue(entry: any, digits = 0) {
  let current = entry
  let raw = entry?.value
  let unit = String(entry?.unit || '').trim()

  // Some snapshot payloads may wrap the actual lab payload in an extra { value } layer.
  while (raw && typeof raw === 'object' && !Array.isArray(raw)) {
    current = raw
    raw = raw?.value
    if (!unit) unit = String(current?.unit || '').trim()
  }

  if (raw == null || raw === '') return ''
  const num = Number(raw)
  if (Number.isFinite(num)) {
    const valueText = digits > 0 ? num.toFixed(digits) : (Math.abs(num - Math.round(num)) < 0.05 ? String(Math.round(num)) : num.toFixed(1))
    return unit ? `${valueText}${unit}` : valueText
  }
  return unit ? `${raw}${unit}` : String(raw)
}

function summaryVitals(card: any) {
  const vitals = summarySnapshot(card)?.vitals || {}
  const defs = [
    { key: 'hr', label: 'HR', digits: 0 },
    { key: 'rr', label: 'RR', digits: 0 },
    { key: 'map', label: 'MAP', digits: 0 },
    { key: 'spo2', label: 'SpO₂', digits: 0 },
    { key: 'temp', label: 'T', digits: 1 },
  ]
  return defs.map((def) => {
    const value = snapshotValue(vitals?.[def.key], def.digits)
    return value ? { label: def.label, value } : null
  }).filter(Boolean) as Array<{ label: string; value: string }>
}

function summaryLabs(card: any) {
  const labs = summarySnapshot(card)?.labs || {}
  const defs = [
    { key: 'lac', label: 'Lac', digits: 1 },
    { key: 'cr', label: 'Cr', digits: 0 },
    { key: 'pct', label: 'PCT', digits: 2 },
  ]
  return defs.map((def) => {
    const value = snapshotValue(labs?.[def.key], def.digits)
    return value ? { label: def.label, value } : null
  }).filter(Boolean) as Array<{ label: string; value: string }>
}

function summaryVaso(card: any) {
  const rows = summarySnapshot(card)?.vasopressors
  if (!Array.isArray(rows)) return []
  return rows.map((row: any) => {
    const drug = String(row?.drug || row?.raw_name || '').trim()
    if (!drug) return null
    return { drug, dose: String(row?.dose_display || row?.route || '在用').trim() }
  }).filter(Boolean) as Array<{ drug: string; dose: string }>
}

function summarySnapshotRows(card: any) {
  const rows = [...summaryVitals(card), ...summaryLabs(card)]
  if (rows.length) return rows.slice(0, 6)
  const postExtub = postExtubationSnapshot(card)
  if (!postExtub) return []
  const mapped = [
    postExtub?.rr != null ? { label: 'RR', value: String(postExtub.rr) } : null,
    postExtub?.spo2 != null ? { label: 'SpO₂', value: `${postExtub.spo2}%` } : null,
    postExtub?.hours_since_extubation != null ? { label: '拔管后', value: `${postExtub.hours_since_extubation}h` } : null,
    postExtub?.accessory_muscle_use ? { label: '辅助肌', value: '有' } : null,
  ]
  return mapped.filter(Boolean) as Array<{ label: string; value: string }>
}

function snapshotTime(card: any) {
  return noteTimeText(summarySnapshot(card)?.snapshot_time)
}

function isRescueSummary(card: any) {
  const sev = severityTone(card?.severity)
  if (sev !== 'high' && sev !== 'critical') return false
  const haystack = `${String(card?.alert_type || '').toLowerCase()} ${String(card?.rule_id || '').toLowerCase()} ${String(card?.category || '').toLowerCase()}`
  const keywords = [
    'shock', 'sepsis', 'septic', 'cardiac_arrest', 'cardiac', 'pea', 'pe_',
    'embol', 'bleed', 'bleeding', 'resp', 'hypoxia', 'hypotension', 'deterioration', 'multi_organ', 'post_extubation',
  ]
  return keywords.some((key) => haystack.includes(key)) || !!summarySnapshot(card) || !!summaryChain(card)
}

function summaryRescueTitle(card: any) {
  const haystack = `${String(card?.alert_type || '').toLowerCase()} ${String(card?.rule_id || '').toLowerCase()}`
  if (haystack.includes('cardiac_arrest')) return '心脏骤停前高风险'
  if (haystack.includes('shock') || haystack.includes('sepsis') || haystack.includes('septic')) return '循环衰竭 / 脓毒症抢救风险'
  if (haystack.includes('pe_') || haystack.includes('embol')) return '急性肺栓塞高风险'
  if (haystack.includes('bleed')) return '活动性出血风险'
  if (haystack.includes('post_extubation')) return '拔管后再插管高风险'
  if (haystack.includes('resp') || haystack.includes('hypoxia')) return '呼吸衰竭风险'
  return String(card?.title || '综合预警')
}

function groupLabel(raw: any) {
  return formatCompositeGroupLabel(raw)
}

function chainLabel(raw: any) {
  return formatCompositeChainLabel(raw)
}

function severityTone(raw: any) {
  const s = String(raw || '').toLowerCase()
  if (s === 'critical' || s.includes('crit')) return 'critical'
  if (s === 'high' || s.includes('high')) return 'high'
  return 'warning'
}

function severityLabel(raw: any) {
  return formatSeverityLabel(severityTone(raw))
}


function pickVital(...values: any[]) {
  for (const value of values) {
    if (value !== null && value !== undefined && value !== '') return value
  }
  return null
}

function formatVitalNumber(value: any, digits = 0) {
  if (value === null || value === undefined || value === '') return '--'
  const n = Number(value)
  if (!Number.isFinite(n)) return String(value)
  const rounded = Number(n.toFixed(digits))
  if (digits <= 0 || Number.isInteger(rounded)) return String(Math.round(rounded))
  return rounded.toFixed(digits).replace(/\.?0+$/, '')
}

function temp(v: any) {
  if (v == null) return '--'
  const n = Number(v)
  return Number.isNaN(n) ? '--' : n.toFixed(1)
}

function shortDiag(s: string) {
  if (!s) return '无初步诊断'
  const first = s.split('|')[0] ?? s
  return first.length > 20 ? `${first.slice(0, 20)}…` : first
}

function patientDiet(patient: any) {
  return String(patient?.diet || patient?.dietType || patient?.nutritionType || '').trim()
}

function noteTimeText(v: any) {
  if (!v) return ''
  const dt = new Date(v)
  if (Number.isNaN(dt.getTime())) return ''
  const mm = String(dt.getMonth() + 1).padStart(2, '0')
  const dd = String(dt.getDate()).padStart(2, '0')
  const hh = String(dt.getHours()).padStart(2, '0')
  const mi = String(dt.getMinutes()).padStart(2, '0')
  return `${mm}-${dd} ${hh}:${mi}`
}


function bundleLights(patient: any) {
  const lights = patient?.bundleStatus?.lights || {}
  const items = [
    { key: 'A', name: '镇痛' }, { key: 'B', name: '呼吸' },
    { key: 'C', name: '镇静' }, { key: 'D', name: '谵妄' },
    { key: 'E', name: '活动' }, { key: 'F', name: '家属' }
  ]
  const stateMap: Record<string, string> = { green: '依从', yellow: '部分', red: '未评', unknown: '空' }
  return items.map(i => ({ ...i, state: lights[i.key] || 'unknown', statusText: stateMap[lights[i.key]] || '未知' }))
}
</script>

<style scoped>
@import url('../../assets/fonts/rajdhani/rajdhani.css');

.card {
  width: 100%;
  min-height: 520px;
  max-height: none;
  background:
    radial-gradient(circle at top right, rgba(56, 189, 248, 0.12) 0%, rgba(56, 189, 248, 0) 28%),
    linear-gradient(180deg, rgba(7, 20, 34, 0.98) 0%, rgba(4, 12, 22, 0.99) 100%);
  border-radius: 12px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  cursor: pointer;
  transition: transform 0.22s ease, box-shadow 0.22s ease, border-color 0.22s ease;
  overflow-y: auto;
  scrollbar-width: none;
  border: 1px solid rgba(77, 196, 255, 0.16);
  box-shadow: 0 14px 32px rgba(2, 6, 23, 0.38);
  position: relative;
  font-family: var(--app-display-font);
}
.card::-webkit-scrollbar { display: none; }
.card:hover {
  transform: translateY(-2px);
  border-color: rgba(103, 232, 249, 0.34);
  box-shadow: 0 20px 38px rgba(2, 6, 23, 0.5), 0 0 18px rgba(34, 211, 238, 0.1);
}
.card:hover .hover-drawer {
  opacity: 1;
  transform: translateY(0);
}

.card::before {
  content: "";
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 4px;
  border-top-left-radius: 14px;
  border-bottom-left-radius: 14px;
  background: transparent;
}
.card::after {
  content: '';
  position: absolute;
  inset: 10px;
  border: 1px solid rgba(72, 193, 255, 0.06);
  border-radius: 10px;
  pointer-events: none;
}
.card .sec-top::before,
.card .sec-footer::after {
  content: '';
  display: block;
  width: 34px;
  height: 1px;
  background: linear-gradient(90deg, rgba(103, 232, 249, 0.34), rgba(103, 232, 249, 0));
}
.card .sec-top::before {
  margin-bottom: 2px;
}
.card .sec-footer::after {
  align-self: flex-end;
  margin-top: 2px;
}
.card--critical::before { background: linear-gradient(180deg, #fb7185 0%, #ef4444 100%); }
.card--high::before { background: linear-gradient(180deg, #fb923c 0%, #f97316 100%); }
.card--warning::before { background: linear-gradient(180deg, #fbbf24 0%, #f59e0b 100%); }
.card--normal::before { background: linear-gradient(180deg, #34d399 0%, #10b981 100%); }
.card--none::before { background: linear-gradient(180deg, #38bdf8 0%, #0ea5e9 100%); }
.card--flash {
  animation: card-pulse 1.8s ease-in-out infinite;
}
@keyframes card-pulse {
  0%, 100% { box-shadow: 0 14px 32px rgba(2, 6, 23, 0.38); }
  50% { box-shadow: 0 18px 40px rgba(239, 68, 68, 0.24), 0 0 24px rgba(251, 90, 122, 0.12); }
}

section { display: flex; flex-direction: column; gap: 7px; }

.card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}
.patient-identity {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  min-width: 0;
}
.bed-no {
  min-width: 54px;
  padding: 6px 10px;
  border-radius: 10px;
  background: linear-gradient(180deg, rgba(9, 45, 70, 0.98) 0%, rgba(6, 25, 42, 0.98) 100%);
  border: 1px solid rgba(90, 214, 255, 0.26);
  color: #82f7ff;
  font-family: 'SF Mono', 'Consolas', monospace;
  font-size: 13px;
  font-weight: 800;
  line-height: 1;
  text-align: center;
  box-shadow: inset 0 0 12px rgba(34, 211, 238, 0.08);
}
.identity-copy {
  min-width: 0;
  flex: 1;
}
.monitor-line {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}
.monitor-label,
.monitor-code {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.16em;
  color: #5de6ef;
}
.monitor-code {
  color: #7dd3fc;
}
.monitor-sep {
  flex: 1;
  height: 1px;
  background: linear-gradient(90deg, rgba(93, 230, 239, 0.34), rgba(93, 230, 239, 0));
}
.name-row {
  display: flex;
  align-items: baseline;
  gap: 10px;
  min-width: 0;
}
.patient-name {
  font-size: 18px;
  font-weight: 800;
  color: #eefcff;
  margin: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  letter-spacing: 0.02em;
}
.patient-meta {
  font-size: 12px;
  color: #8ea9c3;
  font-weight: 600;
  white-space: nowrap;
}
.diag-text {
  margin: 4px 0 0;
  font-size: 11px;
  color: #9ec0da;
  line-height: 1.45;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.monitor-meta-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}
.monitor-meta-chip {
  display: inline-flex;
  align-items: center;
  min-height: 20px;
  padding: 0 8px;
  border-radius: 999px;
  background: rgba(8, 31, 47, 0.72);
  border: 1px solid rgba(80, 199, 255, 0.1);
  color: #8fd4e6;
  font-size: 10px;
  line-height: 1.3;
}
.monitor-meta-chip--rescue {
  color: #fda4af;
  border-color: rgba(251, 113, 133, 0.2);
  background: rgba(71, 16, 28, 0.72);
}
.status-badge {
  flex-shrink: 0;
  min-width: 74px;
  min-height: 40px;
  padding: 8px 10px;
  border-radius: 10px;
  border: 1px solid transparent;
  background:
    linear-gradient(180deg, rgba(10, 33, 50, 0.94) 0%, rgba(7, 23, 38, 0.98) 100%);
  color: #cbd5e1;
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
  box-shadow: inset 0 0 0 1px rgba(109, 216, 255, 0.05);
}
.status-badge strong {
  font-size: 13px;
  line-height: 1.1;
  letter-spacing: 0.04em;
}
.status-badge--critical { background: rgba(71, 16, 28, 0.9); border-color: rgba(248, 113, 113, 0.34); color: #ff98aa; box-shadow: 0 0 16px rgba(251, 90, 122, 0.1); }
.status-badge--high { background: rgba(71, 36, 10, 0.88); border-color: rgba(251, 146, 60, 0.34); color: #ffb36c; }
.status-badge--warning { background: rgba(75, 54, 10, 0.88); border-color: rgba(251, 191, 36, 0.34); color: #ffd66b; }
.status-badge--normal { background: rgba(7, 63, 55, 0.88); border-color: rgba(45, 212, 191, 0.3); color: #56f0c7; }
.status-badge--none { background: rgba(8, 28, 44, 0.88); border-color: rgba(56, 189, 248, 0.2); color: #99dfff; }

.patient-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.allergy-tag {
  font-size: 11px;
  font-weight: 700;
  background: rgba(71, 16, 28, 0.84);
  border: 1px solid rgba(248, 113, 113, 0.24);
  color: #ff95a8;
  padding: 5px 10px;
  border-radius: 8px;
}

.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.section-title {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.16em;
  color: #68f5ff;
  text-transform: uppercase;
}
.section-desc {
  font-size: 10px;
  color: #72a7c5;
}

.sec-vitals,
.sec-risk-fingerprint,
.sec-rescue-spotlight,
.sec-logistics,
.sec-alerts,
.sec-summary,
.sec-footer {
  padding: 9px;
  background: linear-gradient(180deg, rgba(5, 18, 31, 0.92) 0%, rgba(7, 16, 28, 0.86) 100%);
  border: 1px solid rgba(71, 196, 255, 0.12);
  border-radius: 10px;
  box-shadow: inset 0 1px 0 rgba(171, 237, 255, 0.04);
}
.sec-rescue-spotlight {
  border-color: rgba(251, 113, 133, 0.16);
  background:
    radial-gradient(circle at top right, rgba(251, 113, 133, 0.1), rgba(251, 113, 133, 0) 28%),
    linear-gradient(180deg, rgba(20, 22, 38, 0.96) 0%, rgba(10, 15, 28, 0.98) 100%);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.03), 0 10px 22px rgba(244, 63, 94, 0.08);
}
.rescue-spotlight-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
}
.rescue-spotlight-tag {
  display: inline-flex;
  align-items: center;
  min-height: 18px;
  padding: 0 8px;
  border-radius: 999px;
  background: rgba(74, 19, 31, 0.86);
  border: 1px solid rgba(251, 113, 133, 0.18);
  color: #fda4af;
  font-size: 9px;
  letter-spacing: .12em;
}
.rescue-spotlight-sev {
  display: inline-flex;
  align-items: center;
  min-height: 18px;
  padding: 0 8px;
  border-radius: 999px;
  border: 1px solid transparent;
  font-size: 9px;
  font-weight: 700;
}
.rescue-spotlight-sev--warning { color: #fcd34d; background: #3f2d07; border-color: #6a4b0d; }
.rescue-spotlight-sev--high { color: #fdba74; background: #41210b; border-color: #7c3816; }
.rescue-spotlight-sev--critical { color: #fda4af; background: #47131d; border-color: #7f1d32; }
.rescue-spotlight-title {
  color: #ffe4ea;
  font-size: 12px;
  font-weight: 700;
}
.rescue-spotlight-main {
  padding: 8px 10px;
  border-radius: 10px;
  border: 1px solid rgba(251, 113, 133, 0.16);
  background: linear-gradient(180deg, rgba(58, 16, 29, 0.72) 0%, rgba(24, 20, 34, 0.82) 100%);
  color: #fff1f3;
  font-size: 12px;
  line-height: 1.5;
  font-weight: 700;
}
.rescue-spotlight-suggestion {
  padding: 7px 9px;
  border-radius: 9px;
  background: linear-gradient(180deg, rgba(8, 38, 30, 0.72) 0%, rgba(6, 27, 22, 0.82) 100%);
  border: 1px solid rgba(55, 199, 147, 0.16);
  color: #b4f3ca;
  font-size: 10px;
  line-height: 1.5;
  font-weight: 600;
}
.vital-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}
.risk-fingerprint {
  display: grid;
  grid-template-columns: 104px minmax(0, 1fr);
  gap: 10px;
  align-items: center;
}
.risk-fingerprint__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.risk-fingerprint__chip {
  display: inline-flex;
  align-items: center;
  min-height: 26px;
  padding: 0 10px;
  border-radius: 999px;
  background: rgba(8, 28, 44, 0.82);
  border: 1px solid rgba(80,199,255,.14);
  color: #dffbff;
  font-size: 11px;
}
.risk-fingerprint__chip.is-warning { color: #fde68a; border-color: rgba(245,158,11,.22); }
.risk-fingerprint__chip.is-high { color: #fed7aa; border-color: rgba(249,115,22,.24); }
.risk-fingerprint__chip.is-critical { color: #fecdd3; border-color: rgba(244,63,94,.24); }
.vital-item {
  min-height: 76px;
  padding: 10px 12px;
  border-radius: 10px;
  background: linear-gradient(180deg, rgba(8, 31, 49, 0.98) 0%, rgba(6, 21, 35, 0.98) 100%);
  border: 1px solid rgba(71, 196, 255, 0.14);
  display: flex;
  flex-direction: column;
  justify-content: flex-start;
  align-items: flex-start;
  gap: 14px;
  box-shadow: inset 0 0 0 1px rgba(11, 71, 95, 0.2);
}
.v-label {
  font-size: 12px;
  color: #7ecce1;
  font-weight: 400;
  letter-spacing: 0.04em;
}
.v-val {
  display: inline-flex;
  align-items: flex-end;
  font-size: 32px;
  font-weight: 500;
  font-family: "DIN Alternate", "Roboto Mono", "SF Mono", "Consolas", monospace;
  color: #ecfeff;
  line-height: 1.02;
  font-variant-numeric: tabular-nums;
  word-break: break-all;
  letter-spacing: -0.5px;
  text-shadow: 0 0 10px rgba(110, 231, 249, 0.12);
}
.vital-item--bp .v-val {
  font-size: 26px;
}
.v-val small {
  font-size: 14px;
  opacity: 0.72;
  margin-left: 6px;
  margin-bottom: 3px;
  font-weight: 600;
}
.vital--orange {
  background: linear-gradient(180deg, rgba(88, 46, 12, 0.94) 0%, rgba(36, 25, 12, 0.92) 100%);
  border-color: rgba(251, 146, 60, 0.28);
  box-shadow: inset 0 0 0 1px rgba(251, 146, 60, 0.12), 0 0 12px rgba(251, 146, 60, 0.08);
}
.vital--orange .v-label,
.vital--orange .v-val { color: #fdba74; }
.vital--red {
  background: linear-gradient(180deg, rgba(87, 17, 33, 0.94) 0%, rgba(46, 11, 20, 0.92) 100%);
  border-color: rgba(248, 113, 113, 0.28);
  box-shadow: inset 0 0 0 1px rgba(248, 113, 113, 0.12), 0 0 14px rgba(248, 113, 113, 0.08);
}
.vital--red .v-label,
.vital--red .v-val { color: #fda4af; }

.sec-logistics,
.sec-alerts {
  gap: 10px;
}
.info-block {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.info-label {
  font-size: 10px;
  color: #7f91ab;
  font-weight: 700;
  letter-spacing: 0.08em;
}
.device-list,
.tube-list,
.footer-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.device-tag,
.tube-item,
.pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  border-radius: 8px;
  background: rgba(8, 30, 46, 0.88);
  border: 1px solid rgba(71, 196, 255, 0.12);
  color: #d9f9ff;
  font-size: 10px;
  line-height: 1.2;
}
.dev-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #3ee7c0;
  display: inline-block;
  box-shadow: 0 0 0 4px rgba(62, 231, 192, 0.12);
}
.tube-list--folded {
  max-height: 72px;
  overflow: hidden;
}
.tube-item {
  color: #bcecff;
}
.tube--orange {
  background: rgba(76, 43, 12, 0.92);
  color: #fdba74;
  border-color: rgba(251, 146, 60, 0.22);
}
.tube--red {
  background: rgba(70, 16, 28, 0.92);
  color: #fda4af;
  border-color: rgba(248, 113, 113, 0.22);
}
.tube-toggle {
  align-self: flex-start;
  padding: 0;
  border: none;
  background: transparent;
  color: #67e8f9;
  font-size: 10px;
  font-weight: 700;
  cursor: pointer;
}

.alert-line {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  color: #d7fbff;
}
.alert-card {
  display: grid;
  gap: 6px;
  padding: 9px 10px;
  border-radius: 10px;
  border: 1px solid rgba(80, 199, 255, 0.12);
  background:
    linear-gradient(180deg, rgba(8, 28, 44, 0.9) 0%, rgba(5, 18, 31, 0.94) 100%);
  box-shadow: inset 0 1px 0 rgba(145, 228, 255, 0.04);
}
.alert-card--high {
  border-color: rgba(249, 115, 22, 0.24);
}
.alert-card--critical {
  border-color: rgba(251, 90, 122, 0.26);
}
.alert-card-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.alert-card-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.alert-card-title {
  color: #ebfbff;
  font-size: 11px;
  font-weight: 700;
  line-height: 1.35;
}
.alert-card-time {
  flex-shrink: 0;
  color: #78bfd2;
  font-size: 10px;
  font-family: 'SF Mono', 'Consolas', monospace;
}
.alert-card-summary,
.alert-text {
  font-size: 11px;
  line-height: 1.4;
  color: #c7e6f5;
}
.alert-card-summary--rescue {
  color: #fff1f3;
  font-weight: 700;
}
.alert-card-evidence {
  margin: 0;
  padding-left: 16px;
  color: #d3ecfb;
  font-size: 10px;
  line-height: 1.45;
}
.alert-card-evidence li + li {
  margin-top: 2px;
}
.alert-card-suggestion {
  color: #90e7ff;
  font-size: 10px;
  line-height: 1.45;
}
.alert-card-suggestion--rescue {
  color: #baf2cb;
  font-weight: 600;
}
.alert-dot {
  width: 8px;
  height: 8px;
  margin-top: 5px;
  border-radius: 50%;
  flex-shrink: 0;
}
.alert-dot--red { background: #fb7185; }
.alert-dot--yellow { background: #fbbf24; box-shadow: 0 0 8px rgba(251, 191, 36, 0.32); }
.alert-dot--high { background: #fb923c; box-shadow: 0 0 8px rgba(251, 146, 60, 0.3); }
.alert-dot--critical { background: #fb5a7a; box-shadow: 0 0 8px rgba(251, 90, 122, 0.36); }

.sec-summary {
  gap: 8px;
}
.summary-top,
.summary-chain {
  display: grid;
  gap: 6px;
}
.summary-top--rescue {
  padding: 8px 10px;
  border-radius: 10px;
  border: 1px solid rgba(251, 113, 133, 0.16);
  background: linear-gradient(180deg, rgba(55, 16, 28, 0.54) 0%, rgba(18, 17, 30, 0.78) 100%);
}
.summary-rescue-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
}
.summary-rescue-tag {
  display: inline-flex;
  align-items: center;
  min-height: 18px;
  padding: 0 8px;
  border-radius: 999px;
  background: rgba(74, 19, 31, 0.86);
  border: 1px solid rgba(251, 113, 133, 0.18);
  color: #fda4af;
  font-size: 9px;
  letter-spacing: .12em;
}
.summary-rescue-sev {
  display: inline-flex;
  align-items: center;
  min-height: 18px;
  padding: 0 8px;
  border-radius: 999px;
  border: 1px solid transparent;
  font-size: 9px;
  font-weight: 700;
}
.summary-rescue-sev--warning { color: #fcd34d; background: #3f2d07; border-color: #6a4b0d; }
.summary-rescue-sev--high { color: #fdba74; background: #41210b; border-color: #7c3816; }
.summary-rescue-sev--critical { color: #fda4af; background: #47131d; border-color: #7f1d32; }
.summary-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.summary-title {
  color: #ebfbff;
  font-size: 12px;
  font-weight: 700;
  line-height: 1.35;
}
.summary-main-wrap {
  display: grid;
  gap: 6px;
}
.summary-main-wrap--rescue {
  gap: 7px;
}
.summary-block-label {
  color: #8fe6f4;
  font-size: 9px;
  font-weight: 700;
  letter-spacing: .12em;
  text-transform: uppercase;
}
.summary-main {
  padding: 8px 10px;
  border-radius: 10px;
  border: 1px solid rgba(80, 199, 255, 0.12);
  background: linear-gradient(180deg, rgba(8, 29, 44, 0.88) 0%, rgba(6, 20, 33, 0.92) 100%);
  color: #edfaff;
  font-size: 11px;
  line-height: 1.5;
  font-weight: 700;
}
.summary-main--rescue {
  background: linear-gradient(180deg, rgba(58, 16, 29, 0.74) 0%, rgba(25, 20, 34, 0.82) 100%);
  border-color: rgba(251, 113, 133, 0.18);
  color: #fff1f3;
}
.summary-chain {
  padding: 8px 10px;
  border-radius: 10px;
  border: 1px solid rgba(80, 199, 255, 0.12);
  background: linear-gradient(180deg, rgba(7, 24, 39, 0.86) 0%, rgba(7, 18, 30, 0.92) 100%);
}
.summary-chain-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.summary-chain-tag {
  color: #72e4f7;
  font-size: 9px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}
.summary-chain-code {
  color: #9dd8ff;
  font-size: 9px;
  padding: 3px 8px;
  border-radius: 999px;
  border: 1px solid rgba(80, 199, 255, 0.12);
  background: rgba(8, 28, 44, 0.78);
}
.summary-chain-text {
  color: #e9fbff;
  font-size: 10px;
  line-height: 1.5;
  font-weight: 600;
}
.summary-chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.summary-chip-row .summary-block-label {
  width: 100%;
  margin-bottom: 1px;
}
.summary-chip-row--inline {
  margin-top: 2px;
}
.summary-chip-row--rescue .summary-chip {
  border-color: rgba(96, 165, 250, 0.18);
  background: rgba(12, 31, 50, 0.9);
}
.summary-chip {
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  padding: 0 9px;
  border-radius: 999px;
  font-size: 10px;
  line-height: 1.4;
  border: 1px solid rgba(80, 199, 255, 0.12);
  background: rgba(11, 35, 54, 0.84);
  color: #dffbff;
}
.summary-chip--rescue {
  color: #edf7ff;
}
.summary-chip--group {
  font-weight: 700;
}
.summary-chip--warning { color: #fcd34d; border-color: rgba(245, 158, 11, 0.2); }
.summary-chip--high { color: #fdba74; border-color: rgba(249, 115, 22, 0.24); }
.summary-chip--critical { color: #fda4af; border-color: rgba(244, 63, 94, 0.24); }
.summary-suggestion {
  padding: 8px 10px;
  border-radius: 10px;
  background: rgba(8, 38, 56, 0.82);
  border: 1px solid rgba(62, 215, 255, 0.12);
  color: #96efff;
  font-size: 10px;
  line-height: 1.65;
}
.summary-suggestion--rescue {
  background: linear-gradient(180deg, rgba(8, 38, 30, 0.72) 0%, rgba(6, 27, 22, 0.82) 100%);
  border-color: rgba(55, 199, 147, 0.16);
  color: #b4f3ca;
  font-weight: 600;
}
.summary-snapshot {
  display: grid;
  gap: 6px;
  padding: 8px 10px;
  border-radius: 10px;
  border: 1px solid rgba(80, 199, 255, 0.12);
  background: linear-gradient(180deg, rgba(7, 24, 39, 0.88) 0%, rgba(7, 18, 30, 0.94) 100%);
}
.summary-snapshot-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.summary-snapshot-row {
  display: grid;
  grid-template-columns: 40px 1fr;
  gap: 8px;
  align-items: flex-start;
}
.summary-snapshot-label {
  color: #8ed8ee;
  font-size: 9px;
  letter-spacing: 0.1em;
  padding-top: 4px;
  text-transform: uppercase;
}
.summary-snapshot-chip-row,
.summary-snapshot-badge-row,
.summary-mini-snapshot {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.summary-mini-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 22px;
  padding: 0 9px;
  border-radius: 999px;
  border: 1px solid rgba(80, 199, 255, 0.12);
  background: rgba(11, 35, 54, 0.84);
}
.summary-mini-chip--lab {
  border-color: rgba(96, 165, 250, 0.18);
  background: rgba(12, 31, 50, 0.9);
}
.summary-mini-chip-label {
  color: #84bfd7;
  font-size: 9px;
}
.summary-mini-chip-value {
  color: #effbff;
  font-size: 10px;
  font-family: 'Segoe UI', 'Noto Sans SC', 'JetBrains Mono', 'Consolas', monospace;
  font-weight: 700;
}
.summary-vaso-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 20px;
  padding: 0 8px;
  border-radius: 999px;
  border: 1px solid rgba(245, 158, 11, 0.2);
  background: rgba(51, 27, 7, 0.66);
}
.summary-vaso-name {
  color: #fde68a;
  font-size: 10px;
  font-weight: 700;
}
.summary-vaso-dose {
  color: #ffe9b2;
  font-size: 10px;
  font-family: 'Segoe UI', 'Noto Sans SC', 'JetBrains Mono', 'Consolas', monospace;
}
.hover-drawer {
  position: absolute;
  right: 12px;
  top: 12px;
  width: min(320px, calc(100% - 24px));
  padding: 12px;
  border-radius: 12px;
  border: 1px solid rgba(251, 113, 133, 0.16);
  background:
    radial-gradient(circle at top right, rgba(251, 113, 133, 0.1), rgba(251, 113, 133, 0) 28%),
    linear-gradient(180deg, rgba(11, 23, 38, 0.98) 0%, rgba(6, 13, 24, 0.99) 100%);
  box-shadow: 0 16px 36px rgba(2, 6, 23, 0.62);
  display: grid;
  gap: 8px;
  opacity: 0;
  transform: translateY(8px);
  pointer-events: none;
  transition: opacity 0.22s ease, transform 0.22s ease;
  z-index: 8;
}
.hover-drawer--rescue {
  border-color: rgba(251, 113, 133, 0.22);
  box-shadow: 0 22px 44px rgba(2, 6, 23, 0.6), 0 0 28px rgba(244, 63, 94, 0.16);
}
.hover-drawer-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.hover-drawer-tag {
  color: #fda4af;
  font-size: 9px;
  letter-spacing: 0.14em;
}
.hover-drawer-sev {
  display: inline-flex;
  align-items: center;
  min-height: 20px;
  padding: 0 8px;
  border-radius: 999px;
  border: 1px solid transparent;
  font-size: 9px;
  font-weight: 700;
}
.hover-drawer-sev--warning { color: #fcd34d; background: #3f2d07; border-color: #6a4b0d; }
.hover-drawer-sev--high { color: #fdba74; background: #41210b; border-color: #7c3816; }
.hover-drawer-sev--critical { color: #fda4af; background: #47131d; border-color: #7f1d32; }
.hover-drawer-title {
  color: #ffe4ea;
  font-size: 12px;
  font-weight: 700;
}
.hover-drawer-block {
  display: grid;
  gap: 6px;
  padding: 8px 9px;
  border-radius: 10px;
  border: 1px solid rgba(80, 199, 255, 0.12);
  background: rgba(9, 27, 42, 0.76);
}
.hover-drawer-block--summary {
  border-color: rgba(251, 113, 133, 0.16);
  background: linear-gradient(180deg, rgba(58, 16, 29, 0.72) 0%, rgba(24, 20, 34, 0.82) 100%);
}
.hover-drawer-block--snapshot {
  border-color: rgba(96, 165, 250, 0.16);
  background: linear-gradient(180deg, rgba(9, 29, 46, 0.92) 0%, rgba(7, 19, 34, 0.96) 100%);
}
.hover-drawer-block--chain {
  background: linear-gradient(180deg, rgba(11, 31, 49, 0.92) 0%, rgba(6, 21, 36, 0.96) 100%);
}
.hover-drawer-label {
  color: #8fe6f4;
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}
.hover-drawer-main {
  color: #fff1f3;
  font-size: 13px;
  line-height: 1.5;
  font-weight: 700;
}
.hover-drawer-suggestion {
  padding: 7px 9px;
  border-radius: 9px;
  background: linear-gradient(180deg, rgba(8, 38, 30, 0.72) 0%, rgba(6, 27, 22, 0.82) 100%);
  border: 1px solid rgba(55, 199, 147, 0.16);
  color: #b4f3ca;
  font-size: 10px;
  line-height: 1.5;
  font-weight: 600;
}

.sec-footer {
  margin-top: auto;
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;
  border-top: 1px solid rgba(71, 196, 255, 0.12);
}
.bundle-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
  padding: 8px 10px;
  border-radius: 10px;
  background:
    linear-gradient(180deg, rgba(8, 30, 46, 0.9) 0%, rgba(5, 18, 31, 0.94) 100%);
  border: 1px solid rgba(80, 199, 255, 0.12);
  box-shadow: inset 0 1px 0 rgba(145,228,255,.04);
}
.bundle-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.footer-title {
  font-size: 10px;
  font-weight: 700;
  color: #68f5ff;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}
.bundle-score {
  font-size: 10px;
  font-family: 'SF Mono', 'Consolas', monospace;
  color: #d8f7ff;
  padding: 2px 6px;
  border-radius: 999px;
  background: rgba(7, 22, 36, 0.96);
  border: 1px solid rgba(80, 199, 255, 0.14);
}
.bundle-dots {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  padding-top: 6px;
  border-top: 1px solid rgba(80, 199, 255, 0.08);
}
.mini-dot {
  width: 24px;
  height: 24px;
  border-radius: 8px;
  font-size: 10px;
  font-weight: 800;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  border: 1px solid rgba(255, 255, 255, 0.08);
  font-family: 'Segoe UI', 'Noto Sans SC', sans-serif;
}
.mini--green { background: linear-gradient(180deg, #34d399 0%, #10b981 100%); box-shadow: 0 0 12px rgba(52, 211, 153, 0.16); }
.mini--yellow { background: linear-gradient(180deg, #fbbf24 0%, #f59e0b 100%); box-shadow: 0 0 12px rgba(251, 191, 36, 0.16); }
.mini--red { background: linear-gradient(180deg, #fb7185 0%, #ef4444 100%); box-shadow: 0 0 12px rgba(251, 113, 133, 0.16); }
.mini--unknown { background: rgba(12, 41, 62, 0.9); color: #7ecce1; }

.footer-pills {
  justify-content: flex-end;
  align-items: center;
  align-self: stretch;
  align-content: flex-start;
  max-width: 42%;
}
.pill {
  font-size: 10px;
  font-weight: 700;
}
.pill--severity {
  background: rgba(8, 28, 44, 0.88);
  color: #dff8ff;
}
.pill--severity-critical { background: rgba(70, 16, 28, 0.92); color: #ff98aa; border-color: rgba(248, 113, 113, 0.24); }
.pill--severity-high { background: rgba(76, 43, 12, 0.92); color: #fdba74; border-color: rgba(251, 146, 60, 0.24); }
.pill--severity-warning { background: rgba(75, 54, 10, 0.92); color: #fcd34d; border-color: rgba(251, 191, 36, 0.24); }
.pill--severity-normal { background: rgba(7, 63, 55, 0.92); color: #5eead4; border-color: rgba(45, 212, 191, 0.24); }
.pill--iso { background: rgba(42, 22, 81, 0.9); border-color: rgba(167, 139, 250, 0.24); color: #d0b8ff; }
.pill--diet { background: rgba(8, 56, 42, 0.92); border-color: rgba(74, 222, 128, 0.24); color: #86efac; }
html[data-theme='light'] .card {
  border: 1px solid rgba(0,0,0,0.06);
  border-radius: 14px;
  background:
    radial-gradient(circle at top right, rgba(59, 130, 246, 0.08), rgba(59, 130, 246, 0) 30%),
    linear-gradient(180deg, rgba(255,255,255,.99) 0%, rgba(248,250,253,.99) 100%);
  box-shadow: 0 12px 24px rgba(15,23,42,.06), 0 2px 6px rgba(15,23,42,.04);
}
html[data-theme='light'] .card::after {
  display: none;
}
html[data-theme='light'] .card::before {
  width: 4px;
}
html[data-theme='light'] .card--critical::before { background: #EF4444; }
html[data-theme='light'] .card--high::before { background: #F97316; }
html[data-theme='light'] .card--warning::before { background: #EAB308; }
html[data-theme='light'] .card--normal::before { background: #22C55E; }
html[data-theme='light'] .card--none::before { background: #94A3B8; }
html[data-theme='light'] .card--critical {
  background:
    radial-gradient(circle at top right, rgba(239, 68, 68, 0.09), rgba(239, 68, 68, 0) 30%),
    linear-gradient(180deg, rgba(255,255,255,.99) 0%, rgba(255,247,247,.99) 100%);
  border-color: rgba(248, 113, 113, 0.24);
}
html[data-theme='light'] .card--high,
html[data-theme='light'] .card--warning {
  background:
    radial-gradient(circle at top right, rgba(245, 158, 11, 0.09), rgba(245, 158, 11, 0) 30%),
    linear-gradient(180deg, rgba(255,255,255,.99) 0%, rgba(255,251,235,.99) 100%);
}
html[data-theme='light'] .card--high {
  border-color: rgba(251, 146, 60, 0.24);
}
html[data-theme='light'] .card--warning {
  border-color: rgba(245, 158, 11, 0.22);
}
html[data-theme='light'] .card--normal {
  background:
    radial-gradient(circle at top right, rgba(34, 197, 94, 0.08), rgba(34, 197, 94, 0) 28%),
    linear-gradient(180deg, rgba(255,255,255,.99) 0%, rgba(240,253,244,.99) 100%);
  border-color: rgba(74, 222, 128, 0.22);
}
html[data-theme='light'] .card--none {
  border-color: rgba(59, 130, 246, 0.14);
}
html[data-theme='light'] .card--critical .sec-top {
  background:
    radial-gradient(circle at top right, rgba(248, 113, 113, 0.14), rgba(248, 113, 113, 0) 36%),
    linear-gradient(180deg, rgba(255,255,255,.98) 0%, rgba(255,244,246,.98) 100%);
  border-color: rgba(248, 113, 113, 0.2);
}
html[data-theme='light'] .card--high .sec-top,
html[data-theme='light'] .card--warning .sec-top {
  background:
    radial-gradient(circle at top right, rgba(245, 158, 11, 0.14), rgba(245, 158, 11, 0) 36%),
    linear-gradient(180deg, rgba(255,255,255,.98) 0%, rgba(255,248,238,.98) 100%);
}
html[data-theme='light'] .card--high .sec-top {
  border-color: rgba(251, 146, 60, 0.2);
}
html[data-theme='light'] .card--warning .sec-top {
  border-color: rgba(245, 158, 11, 0.18);
}
html[data-theme='light'] .card--normal .sec-top {
  background:
    radial-gradient(circle at top right, rgba(34, 197, 94, 0.12), rgba(34, 197, 94, 0) 34%),
    linear-gradient(180deg, rgba(255,255,255,.98) 0%, rgba(243,252,247,.98) 100%);
  border-color: rgba(74, 222, 128, 0.18);
}
html[data-theme='light'] .card--none .sec-top {
  background:
    radial-gradient(circle at top right, rgba(59, 130, 246, 0.1), rgba(59, 130, 246, 0) 34%),
    linear-gradient(180deg, rgba(255,255,255,.98) 0%, rgba(244,248,253,.98) 100%);
  border-color: rgba(148, 163, 184, 0.16);
}
html[data-theme='light'] .sec-top {
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 12px;
  padding: 10px 12px;
  box-shadow: inset 0 1px 0 rgba(255,255,255,.7), 0 8px 18px rgba(15,23,42,.04);
}
html[data-theme='light'] .card .sec-top::before {
  width: 100%;
  height: 3px;
  margin-bottom: 8px;
  border-radius: 999px;
  background: linear-gradient(90deg, rgba(59,130,246,.32), rgba(59,130,246,.04));
}
html[data-theme='light'] .card--critical .sec-top::before {
  background: linear-gradient(90deg, rgba(239,68,68,.5), rgba(239,68,68,.08));
}
html[data-theme='light'] .card--high .sec-top::before,
html[data-theme='light'] .card--warning .sec-top::before {
  background: linear-gradient(90deg, rgba(245,158,11,.5), rgba(245,158,11,.08));
}
html[data-theme='light'] .card--normal .sec-top::before {
  background: linear-gradient(90deg, rgba(34,197,94,.45), rgba(34,197,94,.08));
}
html[data-theme='light'] .bed-no {
  background: linear-gradient(180deg, #f1f5f9 0%, #e8eef7 100%);
  border: 1px solid rgba(148, 163, 184, 0.2);
  color: #1f3653;
  box-shadow: none;
}
html[data-theme='light'] .card--critical .bed-no {
  background: linear-gradient(180deg, rgba(254,242,242,.98) 0%, rgba(255,228,230,.98) 100%);
  border-color: rgba(248, 113, 113, 0.24);
  color: #b91c1c;
}
html[data-theme='light'] .card--high .bed-no,
html[data-theme='light'] .card--warning .bed-no {
  background: linear-gradient(180deg, rgba(255,247,237,.98) 0%, rgba(255,237,213,.98) 100%);
  border-color: rgba(251, 146, 60, 0.2);
  color: #c2410c;
}
html[data-theme='light'] .card--normal .bed-no {
  background: linear-gradient(180deg, rgba(240,253,244,.98) 0%, rgba(220,252,231,.98) 100%);
  border-color: rgba(74, 222, 128, 0.22);
  color: #047857;
}
html[data-theme='light'] .monitor-label,
html[data-theme='light'] .monitor-code {
  color: #5f738b;
}
html[data-theme='light'] .monitor-sep {
  background: linear-gradient(90deg, rgba(59, 130, 246, 0.24), rgba(59, 130, 246, 0));
}
html[data-theme='light'] .patient-name,
html[data-theme='light'] .v-val,
html[data-theme='light'] .summary-title,
html[data-theme='light'] .summary-main,
html[data-theme='light'] .summary-chain-text,
html[data-theme='light'] .summary-mini-chip-value,
html[data-theme='light'] .alert-card-title,
html[data-theme='light'] .pill--severity {
  color: #0F172A;
}
html[data-theme='light'] .card--critical .patient-name { color: #991b1b; }
html[data-theme='light'] .card--high .patient-name,
html[data-theme='light'] .card--warning .patient-name { color: #9a3412; }
html[data-theme='light'] .card--normal .patient-name { color: #065f46; }
html[data-theme='light'] .patient-meta,
html[data-theme='light'] .diag-text,
html[data-theme='light'] .monitor-meta-chip,
html[data-theme='light'] .section-desc,
html[data-theme='light'] .v-label,
html[data-theme='light'] .info-label,
html[data-theme='light'] .alert-card-time,
html[data-theme='light'] .alert-card-summary,
html[data-theme='light'] .alert-text,
html[data-theme='light'] .summary-block-label,
html[data-theme='light'] .summary-mini-chip-label,
html[data-theme='light'] .summary-snapshot-label {
  color: #64748B;
}
html[data-theme='light'] .diag-text {
  color: #556b86;
}
html[data-theme='light'] .monitor-meta-chip {
  background: rgba(255,255,255,.98);
  border-color: rgba(148, 163, 184, 0.16);
  color: #556b86;
}
html[data-theme='light'] .monitor-meta-chip--rescue {
  background: rgba(255,241,242,.98);
  border-color: rgba(248, 113, 113, 0.22);
  color: #be123c;
}
html[data-theme='light'] .section-title,
html[data-theme='light'] .footer-title,
html[data-theme='light'] .summary-block-label,
html[data-theme='light'] .summary-chain-tag,
html[data-theme='light'] .hover-drawer-label {
  color: #4f6782;
  letter-spacing: 0;
  text-transform: none;
}
html[data-theme='light'] .sec-vitals {
  background: linear-gradient(180deg, rgba(245,248,252,.98) 0%, rgba(241,245,249,.98) 100%);
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 10px;
}
html[data-theme='light'] .sec-vitals,
html[data-theme='light'] .sec-risk-fingerprint,
html[data-theme='light'] .sec-logistics,
html[data-theme='light'] .sec-alerts,
html[data-theme='light'] .sec-summary,
html[data-theme='light'] .sec-footer,
html[data-theme='light'] .bundle-panel,
html[data-theme='light'] .alert-card,
html[data-theme='light'] .summary-main,
html[data-theme='light'] .summary-chain,
html[data-theme='light'] .summary-chip,
html[data-theme='light'] .summary-mini-chip,
html[data-theme='light'] .device-tag,
html[data-theme='light'] .tube-item,
html[data-theme='light'] .pill,
html[data-theme='light'] .vital-item {
  border-color: rgba(0,0,0,0.06);
  background: #FFFFFF;
  box-shadow: none;
}
html[data-theme='light'] .sec-logistics,
html[data-theme='light'] .sec-alerts,
html[data-theme='light'] .sec-summary,
html[data-theme='light'] .sec-footer {
  background: linear-gradient(180deg, rgba(255,255,255,.98) 0%, rgba(246,249,253,.98) 100%);
}
html[data-theme='light'] .bundle-panel,
html[data-theme='light'] .summary-chain,
html[data-theme='light'] .summary-snapshot,
html[data-theme='light'] .alert-card,
html[data-theme='light'] .summary-mini-chip {
  background: linear-gradient(180deg, rgba(247,248,252,.98) 0%, rgba(240,244,249,.98) 100%);
}
html[data-theme='light'] .card:hover {
  border-color: rgba(59, 130, 246, 0.22);
  box-shadow: 0 18px 30px rgba(37,99,235,.08), 0 4px 12px rgba(15,23,42,.05);
}
html[data-theme='light'] .sec-rescue-spotlight,
html[data-theme='light'] .summary-top--rescue,
html[data-theme='light'] .rescue-spotlight-main,
html[data-theme='light'] .summary-main--rescue {
  border-color: #F5CFCF;
  background: #FDEAEA;
}
html[data-theme='light'] .rescue-spotlight-title,
html[data-theme='light'] .rescue-spotlight-main,
html[data-theme='light'] .alert-card-summary--rescue,
html[data-theme='light'] .summary-main--rescue,
html[data-theme='light'] .hover-drawer-title,
html[data-theme='light'] .hover-drawer-main {
  color: #D63031;
}
html[data-theme='light'] .rescue-spotlight-suggestion,
html[data-theme='light'] .summary-suggestion,
html[data-theme='light'] .summary-suggestion--rescue,
html[data-theme='light'] .hover-drawer-suggestion {
  border-color: #CFE9D8;
  background: #E9F7EF;
  color: #27AE60;
}
html[data-theme='light'] .hover-drawer,
html[data-theme='light'] .hover-drawer-block,
html[data-theme='light'] .hover-drawer-block--snapshot,
html[data-theme='light'] .hover-drawer-block--chain {
  border: 1px solid rgba(0,0,0,0.08);
  background: #ffffff;
  box-shadow: 0 8px 24px rgba(0,0,0,0.12);
}
html[data-theme='light'] .hover-drawer-tag,
html[data-theme='light'] .summary-rescue-tag,
html[data-theme='light'] .rescue-spotlight-tag {
  color: #D63031;
  background: #FDEAEA;
  border-color: #F5CFCF;
}
html[data-theme='light'] .summary-chain-code,
html[data-theme='light'] .bundle-score {
  color: #4A7AFF;
  background: #F0F4FF;
  border-color: #D6E0FF;
}
html[data-theme='light'] .status-badge {
  min-height: 34px;
  min-width: auto;
  padding: 6px 12px;
  border-width: 1px;
  border-style: solid;
  box-shadow: 0 10px 18px rgba(15, 23, 42, 0.08);
}
html[data-theme='light'] .status-badge--critical { background: linear-gradient(180deg, #ef4444 0%, #dc2626 100%); border-color: #ef4444; color: #fff7f7; }
html[data-theme='light'] .status-badge--high { background: linear-gradient(180deg, #f97316 0%, #ea580c 100%); border-color: #f97316; color: #fff7ed; }
html[data-theme='light'] .status-badge--warning { background: linear-gradient(180deg, #f59e0b 0%, #d97706 100%); border-color: #f59e0b; color: #fff8eb; }
html[data-theme='light'] .status-badge--normal { background: linear-gradient(180deg, #22c55e 0%, #16a34a 100%); border-color: #22c55e; color: #f0fdf4; }
html[data-theme='light'] .status-badge--none { background: linear-gradient(180deg, #94a3b8 0%, #64748b 100%); border-color: #94a3b8; color: #f8fafc; }
html[data-theme='light'] .status-badge strong {
  letter-spacing: .02em;
}
html[data-theme='light'] .allergy-tag {
  background: #FEF2F2;
  border-color: #FECACA;
  color: #DC2626;
}
html[data-theme='light'] .vital-item {
  min-height: 88px;
  padding: 12px 14px;
  background: linear-gradient(180deg, rgba(255,255,255,.98) 0%, rgba(246,249,253,.98) 100%);
  border-color: rgba(148, 163, 184, 0.14);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.8);
}
html[data-theme='light'] .vital-item--hr {
  background:
    radial-gradient(circle at top right, rgba(59,130,246,.12), rgba(59,130,246,0) 34%),
    linear-gradient(180deg, rgba(255,255,255,.98) 0%, rgba(243,247,255,.98) 100%);
}
html[data-theme='light'] .vital-item--bp {
  background:
    radial-gradient(circle at top right, rgba(245,158,11,.12), rgba(245,158,11,0) 34%),
    linear-gradient(180deg, rgba(255,255,255,.98) 0%, rgba(255,249,239,.98) 100%);
}
html[data-theme='light'] .vital-item--spo2 {
  background:
    radial-gradient(circle at top right, rgba(6,182,212,.12), rgba(6,182,212,0) 34%),
    linear-gradient(180deg, rgba(255,255,255,.98) 0%, rgba(240,253,255,.98) 100%);
}
html[data-theme='light'] .vital-item--temp {
  background:
    radial-gradient(circle at top right, rgba(139,92,246,.12), rgba(139,92,246,0) 34%),
    linear-gradient(180deg, rgba(255,255,255,.98) 0%, rgba(247,245,255,.98) 100%);
}
html[data-theme='light'] .vital-item--hr .v-label { color: #2563eb; }
html[data-theme='light'] .vital-item--bp .v-label { color: #d97706; }
html[data-theme='light'] .vital-item--spo2 .v-label { color: #0891b2; }
html[data-theme='light'] .vital-item--temp .v-label { color: #7c3aed; }
html[data-theme='light'] .v-val {
  color: #0F172A;
  font-family: 'Rajdhani', 'SF Mono', monospace;
  font-weight: 800;
  text-shadow: none;
}
html[data-theme='light'] .vital-item.vital--orange {
  border-color: rgba(251, 191, 36, 0.2);
  background: linear-gradient(180deg, rgba(255,255,255,.98) 0%, rgba(255,251,235,.98) 100%);
}
html[data-theme='light'] .vital-item.vital--orange .v-label,
html[data-theme='light'] .vital-item.vital--red .v-label {
  color: #5f738b;
}
html[data-theme='light'] .vital-item.vital--orange .v-val {
  color: #D97706;
  font-weight: 700;
  background: rgba(255, 247, 237, 0.98);
  border-radius: 6px;
  padding: 2px 6px;
}
html[data-theme='light'] .vital-item.vital--red {
  border-color: rgba(248, 113, 113, 0.22);
  background: linear-gradient(180deg, rgba(255,255,255,.98) 0%, rgba(254,242,242,.98) 100%);
}
html[data-theme='light'] .vital-item.vital--red .v-val {
  color: #DC2626;
  font-weight: 700;
  background: rgba(255, 241, 242, 0.98);
  border-radius: 6px;
  padding: 2px 6px;
}
html[data-theme='light'] .summary-chip {
  background: linear-gradient(180deg, rgba(239,246,255,.98) 0%, rgba(219,234,254,.98) 100%);
  border-color: rgba(59, 130, 246, 0.18);
  color: #1d4ed8;
}
html[data-theme='light'] .summary-chip--warning,
html[data-theme='light'] .tube--orange {
  background: linear-gradient(180deg, rgba(255,247,237,.98) 0%, rgba(255,237,213,.98) 100%);
  border-color: rgba(251, 146, 60, 0.2);
  color: #E67E22;
}
html[data-theme='light'] .summary-chip--critical,
html[data-theme='light'] .tube--red {
  background: linear-gradient(180deg, rgba(254,242,242,.98) 0%, rgba(255,241,242,.98) 100%);
  border-color: rgba(248, 113, 113, 0.22);
  color: #D63031;
}
html[data-theme='light'] .mini--green { background: #22C55E; box-shadow: none; }
html[data-theme='light'] .mini--yellow { background: #EAB308; box-shadow: none; }
html[data-theme='light'] .mini--red { background: #EF4444; box-shadow: none; }
html[data-theme='light'] .mini--unknown { background: #CBD5E1; color: #475569; box-shadow: none; }
html[data-theme='light'] .tube-toggle {
  color: #2563EB;
}
html[data-theme='light'] .risk-fingerprint__chip {
  background: rgba(255,255,255,.96);
  border-color: rgba(130, 170, 194, 0.24);
  color: #27445b;
}

@media (max-width: 640px) {
  .card {
    padding: 14px;
    border-radius: 12px;
  }
  .patient-name {
    font-size: 16px;
  }
  .v-val {
    font-size: 22px;
  }
  .vital-item--bp .v-val {
    font-size: 18px;
  }
  .sec-footer {
    flex-direction: column;
    align-items: flex-start;
  }
  .summary-snapshot-row {
    grid-template-columns: 1fr;
    gap: 4px;
  }
  .summary-snapshot-label {
    padding-top: 0;
  }
  .hover-drawer {
    display: none;
  }
  .bundle-panel,
  .footer-pills {
    max-width: none;
    width: 100%;
    justify-content: flex-start;
  }
  .risk-fingerprint {
    grid-template-columns: 1fr;
    justify-items: center;
  }
}
</style>





