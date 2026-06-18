<template>
  <div class="mobile-page mobile-patient-detail">
    <section class="mobile-bedside-card">
      <div class="mobile-bedside-card__main">
        <div class="mobile-bed large">{{ bedOf(patient) }}</div>
        <div>
          <div class="mobile-kicker">床头卡</div>
          <h1>{{ patientNameOf(patient) }}</h1>
          <p>{{ diagnosis }}</p>
        </div>
      </div>
      <div class="mobile-bedside-card__actions compact">
        <button type="button" @click="openScan">扫码</button>
        <button type="button" :disabled="interpreting" @click="interpretPatient">{{ interpreting ? '解读中' : '辅助解读' }}</button>
      </div>
      <div class="mobile-chip-row">
        <span v-if="displayText(genderLabel(firstText(patient, ['hisSex', 'sex', 'gender'])))">{{ genderLabel(firstText(patient, ['hisSex', 'sex', 'gender'])) }}</span>
        <span v-if="displayText(ageLabel(firstText(patient, ['age', 'hisAge'])))">{{ ageLabel(firstText(patient, ['age', 'hisAge'])) }}</span>
        <span v-if="displayText(firstText(patient, ['hisDept', 'deptName', 'dept', 'department'], shell.deptLabel.value))">{{ firstText(patient, ['hisDept', 'deptName', 'dept', 'department'], shell.deptLabel.value) }}</span>
        <span :class="`chip-${riskTone}`">{{ riskText }}</span>
      </div>
      <div class="mobile-support-row compact">
        <span v-for="item in supportItems" :key="item.key" :class="{ active: item.active }">{{ item.label }}</span>
      </div>
    </section>

    <section v-if="aiSummary.length" class="mobile-card mobile-ai-brief">
      <div class="mobile-section-head">
        <h2>AI三句摘要</h2>
        <button type="button" @click="aiSummary = []">收起</button>
      </div>
      <p v-for="line in aiSummary" :key="line">{{ line }}</p>
    </section>

    <div class="mobile-segment">
      <button v-for="item in tabs" :key="item.key" type="button" :class="{ active: tab === item.key }" @click="tab = item.key">
        {{ item.label }}
      </button>
    </div>

    <section v-if="tab === 'overview'" class="mobile-card">
      <div class="mobile-section-head">
        <h2>床旁概览</h2>
        <button type="button" @click="loadFastThenFull">刷新</button>
      </div>
      <div class="mobile-bodymap">
        <button
          v-for="organ in organItems"
          :key="organ.key"
          type="button"
          :class="['mobile-organ-dot', { abnormal: organ.abnormal }, `tone-${organ.tone || 'stable'}`]"
          @click="tab = organ.target"
        >
          <b>{{ organ.label }}</b>
          <span>{{ organ.abnormal ? '异常' : '平稳' }}</span>
        </button>
      </div>
      <div class="mobile-info-list readonly">
        <p v-if="displayText(firstText(patient, ['hisPid', 'admission_no', 'patient_id']))"><b>住院号</b><span>{{ firstText(patient, ['hisPid', 'admission_no', 'patient_id']) }}</span></p>
        <p><b>主诊断</b><span>{{ diagnosis }}</span></p>
        <p v-if="displayText(icuDays)"><b>入科天数</b><span>{{ icuDays }}</span></p>
        <p v-if="displayText(firstText(patient, ['apacheII', 'apache_ii', 'apache2']))"><b>APACHE II</b><span>{{ firstText(patient, ['apacheII', 'apache_ii', 'apache2']) }}</span></p>
      </div>
    </section>

    <section v-if="tab === 'alerts'" class="mobile-card">
      <div class="mobile-section-head"><h2>活动告警</h2><button type="button" @click="loadAlerts">刷新</button></div>
      <article v-for="alert in alerts" :key="alertIdOf(alert)" class="mobile-list-row prominent" @click="selectedAlert = alert">
        <i :class="`tone-${toneOf(alert)}`"></i>
        <div>
          <strong>{{ alertTitleOf(alert) }}</strong>
          <p>{{ alertSummaryOf(alert) }}</p>
          <div class="mobile-chip-row"><span :class="`chip-${toneOf(alert)}`">{{ levelLabel(alert) }}</span></div>
        </div>
        <span>{{ formatTime(firstText(alert, ['created_at', 'time', 'timestamp'])) }}</span>
      </article>
      <div v-if="!alerts.length" class="mobile-empty">暂无活动告警</div>
    </section>

    <section v-if="tab === 'trend'" class="mobile-card">
      <div class="mobile-section-head"><h2>24h趋势</h2><button type="button" @click="loadTrend">刷新</button></div>
      <div class="mobile-vital-grid">
        <div v-for="metric in vitalMetrics" :key="metric.key" class="mobile-vital">
          <span>{{ metric.label }}</span>
          <strong>{{ metric.value }}</strong>
          <small>{{ metric.hint }}</small>
        </div>
      </div>
    </section>

    <section v-if="tab === 'orders'" class="mobile-card">
      <div class="mobile-section-head"><h2>检验与医嘱</h2><button type="button" @click="loadOrders">刷新</button></div>
      <h3 class="mobile-subtitle">异常检验</h3>
      <article v-for="lab in labs.slice(0, 8)" :key="JSON.stringify(lab)" class="mobile-mini-row">
        <strong>{{ firstText(lab, ['itemName', 'itemCnName', 'item_name', 'name', 'label'], '检验') }}</strong>
        <span>{{ compactJoin([firstText(lab, ['result', 'resultValue', 'value']), firstText(lab, ['unit', 'resultUnit'])]) }}</span>
      </article>
      <div v-if="!labs.length" class="mobile-empty">暂无检验记录</div>
      <h3 class="mobile-subtitle">活动医嘱</h3>
      <article v-for="drug in drugs.slice(0, 8)" :key="JSON.stringify(drug)" class="mobile-mini-row">
        <strong>{{ firstText(drug, ['drugName', 'drug_name', 'name', 'orderName', 'order_name'], '用药') }}</strong>
        <span>{{ compactJoin([firstText(drug, ['dose', 'drugSpec']), firstText(drug, ['frequency', 'route', 'status'])]) }}</span>
      </article>
      <div v-if="!drugs.length" class="mobile-empty">暂无用药记录</div>
    </section>

    <section v-if="tab === 'handoff'" class="mobile-card">
      <div class="mobile-section-head"><h2>交班 ISBAR</h2><button type="button" @click="loadHandoff">刷新</button></div>
      <div class="mobile-isbar">
        <article v-for="item in isbarItems" :key="item.key" class="mobile-clinical-card" @click="toggleClinicalExpand(`isbar:${item.key}`)">
          <b>{{ item.code || item.key }}</b>
          <div>
            <strong>{{ item.title }}</strong>
            <p :class="{ collapsed: !expandedClinical.has(`isbar:${item.key}`) }">{{ item.text }}</p>
            <div class="mobile-clinical-tags">
              <span v-for="tag in clinicalTags(item)" :key="tag">{{ tag }}</span>
            </div>
          </div>
        </article>
      </div>
    </section>

    <section v-if="tab === 'rounding'" class="mobile-card">
      <div class="mobile-section-head"><h2>ICU查房</h2><button type="button" @click="loadHandoff">刷新</button></div>
      <div class="mobile-rounding-grid">
        <article v-for="item in roundingItems" :key="item.key" class="mobile-clinical-card compact" @click="toggleClinicalExpand(`round:${item.key}`)">
          <b>{{ item.title.slice(0, 2) }}</b>
          <div>
            <strong>{{ item.title }}</strong>
            <p :class="{ collapsed: !expandedClinical.has(`round:${item.key}`) }">{{ item.text }}</p>
            <div class="mobile-clinical-tags">
              <span v-for="tag in clinicalTags(item)" :key="tag">{{ tag }}</span>
            </div>
          </div>
        </article>
      </div>
      <div class="mobile-voice-box">
        <button type="button" :class="{ active: recording }" @click="toggleRecord">{{ recording ? '停止录入' : '语音录入查房' }}</button>
        <textarea v-model="roundingText" placeholder="按 ICU 查房习惯记录：循环、呼吸、感染、肾脏、神经镇静、营养、管路、今日计划"></textarea>
        <button type="button" class="mobile-primary" :disabled="!roundingText.trim() || savingNote" @click="saveRoundingNote">
          {{ savingNote ? '保存中' : '保存ICU查房草稿' }}
        </button>
        <p v-if="roundingStatus">{{ roundingStatus }}</p>
      </div>
    </section>

    <div v-if="scanOpen" class="mobile-drawer-mask" @click.self="scanOpen = false">
      <section class="mobile-drawer">
        <h2>扫码进入床位</h2>
        <p>可扫描床头二维码，或输入二维码里的床号/患者号。</p>
        <input v-model.trim="scanText" placeholder="床号 / 住院号 / 患者ID" @keyup.enter="resolveScanText" />
        <div class="mobile-action-grid">
          <button type="button" @click="startQrScan">调用扫码</button>
          <button type="button" @click="resolveScanText">进入</button>
        </div>
        <p v-if="scanStatus" class="mobile-inline-status">{{ scanStatus }}</p>
      </section>
    </div>

    <div v-if="selectedAlert" class="mobile-drawer-mask" @click.self="selectedAlert = null">
      <section class="mobile-drawer">
        <h2>{{ alertTitleOf(selectedAlert) }}</h2>
        <p>{{ alertSummaryOf(selectedAlert) }}</p>
        <textarea v-model="actionNote" placeholder="处置备注，可选"></textarea>
        <div class="mobile-action-grid">
          <button type="button" @click="ackSelected('acknowledged')">确认</button>
          <button type="button" @click="ackSelected('handoff_doctor')">转医生</button>
          <button type="button" @click="ackSelected('handoff_nurse')">转护士</button>
          <button type="button" @click="disposeSelected('review_later')">1小时复评</button>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  getClinicalPatientHandoff,
  getMobilePatientBedcard,
  getPatientAlerts,
  getPatientDetail,
  getPatientDrugs,
  getPatientLabs,
  getPatientVitalsTrend,
  postAlertAcknowledge,
  postAlertDisposition,
  postMobilePatientInterpret,
  postMobileRoundingNote,
  postPatientAlertsViewed,
  resolveMobilePatient,
} from '../api'
import { useMobileShell } from '../composables/useMobileShell'
import { onAlertMessage } from '../services/alertSocket'
import { buildIcuRoundingSections, buildIsbarSections, formatClinicalText } from '../utils/clinicalHandoffTemplates'
import { MOBILE_ACTION_SOURCE } from './types'
import { ageLabel, alertIdOf, alertSummaryOf, alertTitleOf, arrayFromResponse, bedOf, firstText, formatTime, genderLabel, labelText, levelLabel, patientDiagnosisOf, patientNameOf, toneOf } from './mobileData'
import { alertMatchesPatient, mergeMobileAlert } from './mobileRealtime'

const route = useRoute()
const router = useRouter()
const shell = useMobileShell()
const patient = ref<any>({})
const bedcard = ref<any>({})
const alerts = ref<any[]>([])
const trend = ref<any>({})
const labs = ref<any[]>([])
const drugs = ref<any[]>([])
const handoffRaw = ref<any>(null)
const handoffText = ref('')
const selectedAlert = ref<any | null>(null)
const actionNote = ref('')
const tab = ref('overview')
const aiSummary = ref<string[]>([])
const interpreting = ref(false)
const scanOpen = ref(false)
const scanText = ref('')
const scanStatus = ref('')
const roundingText = ref('')
const roundingStatus = ref('')
const recording = ref(false)
const savingNote = ref(false)
const expandedClinical = ref<Set<string>>(new Set())
let offAlert: (() => void) | null = null
let recognition: any = null

const tabs = [
  { key: 'overview', label: '概览' },
  { key: 'alerts', label: '告警' },
  { key: 'trend', label: '趋势' },
  { key: 'orders', label: '医嘱' },
  { key: 'handoff', label: '交班' },
  { key: 'rounding', label: '查房' },
]
const patientId = computed(() => String(route.params.id || ''))
const diagnosis = computed(() => patientDiagnosisOf(patient.value, '暂无诊断摘要'))
const riskTone = computed(() => toneOf(patient.value))
const riskText = computed(() => labelText(firstText(patient.value, ['risk_level', 'level'], '关注')))
const icuDays = computed(() => {
  const raw = firstText(patient.value, ['icu_days', 'icuDays', 'in_icu_days', 'admitDays'])
  return raw ? `${raw}天` : ''
})
const latestTrendPoint = computed(() => {
  const rows = arrayFromResponse(trend.value, ['points', 'series', 'vitals'])
  return rows[rows.length - 1] || trend.value || {}
})
const vitalMetrics = computed(() => [
  { key: 'hr', label: 'HR', value: firstText(latestTrendPoint.value, ['hr', 'HR'], '未采集'), hint: '心率' },
  { key: 'map', label: 'MAP', value: firstText(latestTrendPoint.value, ['ibp_map', 'nibp_map', 'map', 'MAP'], '未采集'), hint: '平均动脉压' },
  { key: 'spo2', label: 'SpO2', value: firstText(latestTrendPoint.value, ['spo2', 'SpO2'], '未采集'), hint: '血氧' },
  { key: 'rr', label: 'RR', value: firstText(latestTrendPoint.value, ['rr', 'RR'], '未采集'), hint: '呼吸频率' },
])
const supportItems = computed(() => {
  const support = bedcard.value?.support || {}
  return [
    { key: 'ventilator', label: '呼吸机', active: support.ventilator },
    { key: 'crrt', label: 'CRRT', active: support.crrt },
    { key: 'vasopressor', label: '升压药', active: support.vasopressor },
    { key: 'sedation', label: '镇静', active: support.sedation },
  ]
})
const organItems = computed(() => {
  const rows = Array.isArray(bedcard.value?.organs) ? bedcard.value.organs : []
  const map: Record<string, string> = { respiratory: 'trend', circulation: 'trend', renal: 'orders', infection: 'alerts', neuro: 'rounding' }
  if (rows.length) return rows.map((item: any) => ({ ...item, target: map[item.key] || 'alerts' }))
  return [
    { key: 'respiratory', label: '呼吸', abnormal: false, tone: 'stable', target: 'trend' },
    { key: 'circulation', label: '循环', abnormal: false, tone: 'stable', target: 'trend' },
    { key: 'renal', label: '肾脏', abnormal: false, tone: 'stable', target: 'orders' },
    { key: 'infection', label: '感染', abnormal: false, tone: 'stable', target: 'alerts' },
    { key: 'neuro', label: '神经', abnormal: false, tone: 'stable', target: 'rounding' },
  ]
})
const isbarItems = computed(() => buildIsbarSections(patient.value, handoffRaw.value, { alerts: alerts.value, handoffActor: shell.actor.value }))
const roundingItems = computed(() => buildIcuRoundingSections(patient.value, handoffRaw.value?.summary || handoffRaw.value, { alerts: alerts.value }))

function toggleClinicalExpand(key: string) {
  const next = new Set(expandedClinical.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  expandedClinical.value = next
}

function clinicalTags(item: any) {
  const explicit = Array.isArray(item?.items) ? item.items : []
  const text = String(item?.text || '')
  const tags = explicit.length ? explicit : text.split(/[；;，,。.\n]/).map((part) => part.trim()).filter(Boolean)
  return tags.slice(0, 3)
}

function displayText(value: any) {
  const text = String(value ?? '').trim()
  return Boolean(text && text !== '--' && text !== '未采集')
}

function compactJoin(values: any[]) {
  return values.map((item) => String(item ?? '').trim()).filter((item) => item && item !== '--').join(' ') || '未记录'
}

function cacheKey() {
  return `mobile_patient:${patientId.value}`
}

function readCache() {
  try {
    const cached = sessionStorage.getItem(cacheKey())
    if (cached) {
      const parsed = JSON.parse(cached)
      patient.value = parsed.patient || parsed
      bedcard.value = parsed.bedcard || {}
    }
  } catch {
    // Ignore malformed cache.
  }
}

function writeCache() {
  try {
    sessionStorage.setItem(cacheKey(), JSON.stringify({ patient: patient.value, bedcard: bedcard.value, savedAt: Date.now() }))
  } catch {
    // Embedded browsers may disable storage.
  }
}

function readableText(value: any): string {
  if (value == null) return ''
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return String(value).trim()
  if (Array.isArray(value)) return value.map(readableText).filter(Boolean).join('\n')
  if (typeof value === 'object') {
    for (const key of ['handoff_text', 'handoff', 'summary', 'content', 'markdown', 'text', 'narrative', 'brief', 'note']) {
      const text = readableText(value[key])
      if (text) return text
    }
  }
  return ''
}

function scrubClinicalText(value: any) {
  return readableText(value)
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line && !/^(patient_id|role|generated_at|source|data_source|code)\s*[:：]/i.test(line))
    .map((line) => line.replace(/^handoff_text\s*[:：]\s*/i, '').replace(/^story\s*[:：]\s*/i, '').replace(/^summary\s*[:：]\s*/i, ''))
    .filter(Boolean)
    .join('\n')
}

function pickFromObject(data: any, keys: string[]) {
  if (!data || typeof data !== 'object') return ''
  for (const key of keys) {
    const text = scrubClinicalText(data[key])
    if (text) return text
  }
  return ''
}

function buildIsbar(data: any, text: string) {
  const clean = scrubClinicalText(data) || scrubClinicalText(text)
  const patientLine = compactJoin([bedOf(patient.value) ? `${bedOf(patient.value)}床` : '', patientNameOf(patient.value), diagnosis.value])
  const alertsText = alerts.value.slice(0, 2).map((item) => `${levelLabel(item)}：${alertTitleOf(item)}`).join('；')
  return [
    { key: 'I', text: pickFromObject(data, ['identity', 'i']) || patientLine },
    { key: 'S', text: pickFromObject(data, ['situation', 's']) || firstSentence(clean) || '当前无结构化交班摘要，请结合床旁监护复核。' },
    { key: 'B', text: pickFromObject(data, ['background', 'b']) || diagnosis.value },
    { key: 'A', text: pickFromObject(data, ['assessment', 'a']) || alertsText || '暂无高危未闭环事项。' },
    { key: 'R', text: pickFromObject(data, ['recommendation', 'r']) || '优先复核未闭环告警、活动医嘱和今日重点处置。' },
  ]
}
void buildIsbar

function buildRounding(data: any, text: string) {
  const clean = scrubClinicalText(data) || scrubClinicalText(text)
  return [
    { key: 'circulation', label: '循环', text: sectionText(clean, ['循环', '血压', 'MAP', '升压', '乳酸']) || '复核血压/MAP、容量状态、乳酸和升压药。' },
    { key: 'respiratory', label: '呼吸', text: sectionText(clean, ['呼吸', '氧合', 'SpO2', '呼吸机', '气道']) || '复核氧合、呼吸机参数、气道分泌物和撤机条件。' },
    { key: 'infection', label: '感染', text: sectionText(clean, ['感染', '体温', '抗生素', '培养', 'PCT', 'CRP']) || '复核感染灶、培养、抗菌药物和降阶梯机会。' },
    { key: 'renal', label: '肾脏/液体', text: sectionText(clean, ['肾', '尿量', '肌酐', 'CRRT', '出入量']) || '复核尿量、肌酐、电解质、出入量和CRRT需求。' },
    { key: 'neuro', label: '神经镇痛镇静', text: sectionText(clean, ['神经', '镇静', '镇痛', 'RASS', 'CAM', '谵妄']) || '复核RASS/CAM-ICU、镇痛镇静目标和谵妄风险。' },
    { key: 'nutrition', label: '营养/血糖', text: sectionText(clean, ['营养', '血糖', '肠内', '蛋白']) || '复核营养达标、胃肠耐受、血糖和蛋白供给。' },
    { key: 'lines', label: '管路/皮肤', text: sectionText(clean, ['管路', '导管', '皮肤', '压疮', 'VAP', 'CRBSI']) || '复核导管必要性、皮肤压力损伤和Bundle完成度。' },
    { key: 'plan', label: '今日计划', text: sectionText(clean, ['计划', '建议', '处置', '复评']) || '明确今日复查、医嘱草稿、Bundle和告警闭环负责人。' },
  ]
}
void buildRounding

function firstSentence(text: string) {
  return text.split(/[。；\n]/).map((item) => item.trim()).find(Boolean) || ''
}

function sectionText(text: string, keywords: string[]) {
  const rows = text.split('\n').map((line) => line.trim()).filter(Boolean)
  return rows.find((line) => keywords.some((key) => line.toLowerCase().includes(key.toLowerCase()))) || ''
}

async function loadBedcard() {
  const res = await getMobilePatientBedcard(patientId.value)
  bedcard.value = res.data || {}
  patient.value = { ...(patient.value || {}), ...(res.data?.patient || {}) }
  writeCache()
}

async function loadPatient() {
  const res = await getPatientDetail(patientId.value)
  patient.value = { ...(patient.value || {}), ...(res.data?.patient || res.data || {}) }
  writeCache()
}

async function loadAlerts() {
  const res = await getPatientAlerts(patientId.value)
  alerts.value = arrayFromResponse(res.data, ['alerts', 'records'])
  const ids = alerts.value.map(alertIdOf).filter(Boolean)
  if (ids.length) void postPatientAlertsViewed(patientId.value, { alert_ids: ids, actor: shell.actor.value, source: MOBILE_ACTION_SOURCE })
}

async function loadTrend() {
  const res = await getPatientVitalsTrend(patientId.value, '24h')
  trend.value = res.data || {}
}

async function loadOrders() {
  const [labRes, drugRes] = await Promise.allSettled([getPatientLabs(patientId.value), getPatientDrugs(patientId.value)])
  if (labRes.status === 'fulfilled') labs.value = normalizeLabs(labRes.value.data)
  if (drugRes.status === 'fulfilled') drugs.value = arrayFromResponse(drugRes.value.data, ['records', 'drugs', 'orders'])
}

async function loadHandoff() {
  const res = await getClinicalPatientHandoff(patientId.value, { role: shell.role.value, hours: 24 })
  handoffRaw.value = res.data
  handoffText.value = formatClinicalText(res.data)
}

async function loadFastThenFull() {
  readCache()
  await Promise.allSettled([loadBedcard(), loadPatient()])
  void Promise.allSettled([loadAlerts(), loadTrend(), loadOrders(), loadHandoff()])
}

function normalizeLabs(data: any) {
  const rows = arrayFromResponse(data, ['labs', 'items', 'records'])
  if (rows.length) return rows
  const exams = arrayFromResponse(data, ['exams'])
  return exams.flatMap((exam: any) => {
    const items = arrayFromResponse(exam, ['items'])
    return items.map((item: any) => ({ ...item, examName: firstText(exam, ['examName', 'name'], ''), requestTime: firstText(exam, ['requestTime', 'time'], '') }))
  })
}

async function interpretPatient() {
  interpreting.value = true
  try {
    const res = await postMobilePatientInterpret(patientId.value, { actor: shell.actor.value, source: MOBILE_ACTION_SOURCE, hours: 24 })
    const rows = Array.isArray(res.data?.summary) ? res.data.summary : String(res.data?.text || '').split('\n')
    aiSummary.value = rows.map((item: any) => String(item || '').trim()).filter(Boolean).slice(0, 3)
  } finally {
    interpreting.value = false
  }
}

function openScan() {
  scanOpen.value = true
  scanStatus.value = ''
  scanText.value = ''
}

function extractScanValue(text: string) {
  const raw = String(text || '').trim()
  try {
    const url = new URL(raw)
    return url.searchParams.get('patient_id') || url.searchParams.get('patientId') || url.searchParams.get('bed') || url.pathname.split('/').filter(Boolean).pop() || raw
  } catch {
    return raw
  }
}

async function resolveScanText() {
  const q = extractScanValue(scanText.value)
  if (!q) {
    scanStatus.value = '请输入床号或患者号'
    return
  }
  scanStatus.value = '正在定位床位...'
  const res = await resolveMobilePatient(q)
  const id = firstText(res.data?.patient, ['patient_id', '_id', 'id'])
  if (!id) {
    scanStatus.value = res.data?.message || '未找到对应患者'
    return
  }
  scanOpen.value = false
  await router.push({ path: `/m/patient/${id}`, query: shell.identityQuery() })
}

function startQrScan() {
  const wx = (window as any).wx
  const dd = (window as any).dd
  if (wx?.scanQRCode) {
    wx.scanQRCode({
      needResult: 1,
      scanType: ['qrCode', 'barCode'],
      success: (res: any) => {
        scanText.value = res?.resultStr || ''
        void resolveScanText()
      },
    })
    return
  }
  if (dd?.biz?.util?.scan) {
    dd.biz.util.scan({
      type: 'all',
      onSuccess: (res: any) => {
        scanText.value = res?.text || ''
        void resolveScanText()
      },
    })
    return
  }
  scanStatus.value = '当前浏览器不支持直接扫码，请输入床号或患者号'
}

function toggleRecord() {
  const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
  if (!SpeechRecognition) {
    roundingStatus.value = '当前浏览器不支持语音识别，请直接输入查房记录'
    return
  }
  if (recording.value && recognition) {
    recognition.stop()
    return
  }
  recognition = new SpeechRecognition()
  recognition.lang = 'zh-CN'
  recognition.continuous = true
  recognition.interimResults = true
  recognition.onresult = (event: any) => {
    let text = ''
    for (let index = 0; index < event.results.length; index += 1) text += event.results[index][0]?.transcript || ''
    roundingText.value = text
  }
  recognition.onend = () => {
    recording.value = false
  }
  recording.value = true
  recognition.start()
}

async function saveRoundingNote() {
  savingNote.value = true
  roundingStatus.value = ''
  try {
    await postMobileRoundingNote(patientId.value, {
      actor: shell.actor.value,
      source: MOBILE_ACTION_SOURCE,
      text: roundingText.value,
      device_context: { userAgent: navigator.userAgent, viewport: `${window.innerWidth}x${window.innerHeight}`, container: shell.container.value },
    })
    roundingStatus.value = '已保存为ICU查房草稿'
    roundingText.value = ''
  } catch {
    roundingStatus.value = '保存失败，请稍后重试'
  } finally {
    savingNote.value = false
  }
}

async function ackSelected(disposition: string) {
  if (!selectedAlert.value) return
  const id = alertIdOf(selectedAlert.value)
  if (!id) return
  await postAlertAcknowledge(id, { actor: shell.actor.value, note: actionNote.value, disposition, override_reason_text: actionNote.value, source: MOBILE_ACTION_SOURCE } as any)
  alerts.value = alerts.value.filter((item) => alertIdOf(item) !== id)
  selectedAlert.value = null
  actionNote.value = ''
}

async function disposeSelected(action: string) {
  if (!selectedAlert.value) return
  const id = alertIdOf(selectedAlert.value)
  if (!id) return
  await postAlertDisposition(id, { action, reason: actionNote.value, actor: shell.actor.value, review_after_minutes: 60, source: MOBILE_ACTION_SOURCE } as any)
  alerts.value = alerts.value.map((item) => (alertIdOf(item) === id ? { ...item, disposition: action } : item))
  selectedAlert.value = null
  actionNote.value = ''
}

function applyRealtimeAlert(message: any) {
  if (message?.type !== 'alert' || !message.data) return
  const alertPatientId = firstText(message.data, ['patient_id', 'patientId'])
  if (alertPatientId !== patientId.value && !alertMatchesPatient(message.data, patient.value)) return
  alerts.value = mergeMobileAlert(alerts.value, message.data, 60)
}

watch(patientId, loadFastThenFull)
onMounted(() => {
  void loadFastThenFull()
  offAlert = onAlertMessage(applyRealtimeAlert)
  window.addEventListener('mobile:refresh', loadFastThenFull)
})

onUnmounted(() => {
  offAlert?.()
  window.removeEventListener('mobile:refresh', loadFastThenFull)
  if (recognition) recognition.stop()
})
</script>
