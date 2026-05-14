<template>
  <div class="human-demo">
    <header class="human-demo__header">
      <div>
        <span class="human-demo__kicker">ICU Organ Alarm</span>
        <h1>3D / 2D 人体器官报警演示</h1>
      </div>
      <div class="human-demo__toolbar">
        <button
          v-for="item in tierOptions"
          :key="item.value"
          :class="['human-demo__button', { active: forceTier === item.value }]"
          type="button"
          @click="forceTier = item.value"
        >
          {{ item.label }}
        </button>
      </div>
    </header>

    <main class="human-demo__layout">
      <section class="human-demo__top">
        <section class="human-demo__focus human-demo__panel">
          <div class="human-demo__panel-head">
            <strong>最高优先级</strong>
            <span>{{ topAlarm ? levelText(topAlarm.level) : '监测中' }}</span>
          </div>
          <div v-if="topAlarm" class="human-demo__focus-main">
            <b>{{ organLabel(topAlarm.organ) }}</b>
            <span>{{ topAlarm.bed || '--' }}床 {{ topAlarm.patientName || topAlarm.patientId || '聚合视图' }}</span>
            <strong>{{ topAlarm.metric || '指标' }} {{ topAlarm.value ?? '--' }}</strong>
          </div>
          <div v-else class="human-demo__empty">触发报警后显示最高优先级器官。</div>
        </section>

        <section class="human-demo__stage">
        <HumanBody
          :key="forceTier"
          :force-tier="forceTier"
          :patient-id="patientMode ? selectedPatientId : undefined"
          :auto-focus="autoFocus"
          show-labels
          @organ-click="handleOrganClick"
          @ready="ready = true"
          @load-failed="lastEvent = `模型加载失败，已降级：${$event}`"
          @performance-degraded="lastEvent = `性能下降，已切换 2D：${Math.round($event)} FPS`"
        />
      </section>

        <section class="human-demo__stats human-demo__panel">
          <div class="human-demo__panel-head">
            <strong>等级统计</strong>
            <span>{{ visibleAlarms.length }}</span>
          </div>
          <div class="human-demo__stat-row" v-for="row in levelRows" :key="row.label">
            <span :class="['human-demo__dot', row.level]" />
            <span>{{ row.label }}</span>
            <b>{{ row.count }}</b>
          </div>
          <div class="human-demo__dept-list">
            <div v-for="row in demoDeptRows" :key="row.dept" class="human-demo__dept">
              <span>{{ row.dept }}</span>
              <b>{{ row.patientCount }}床</b>
            </div>
          </div>
        </section>
      </section>

      <section class="human-demo__bottom">
        <section class="human-demo__panel">
          <div class="human-demo__panel-head">
            <strong>手动触发</strong>
            <label>
              <input v-model="patientMode" type="checkbox" />
              单患者模式
            </label>
          </div>
          <label class="human-demo__field">
            患者 ID
            <input v-model="selectedPatientId" :disabled="!patientMode" />
          </label>
          <label class="human-demo__field">
            自动聚焦
            <input v-model="autoFocus" type="checkbox" />
          </label>
          <div class="human-demo__organ-grid">
            <button
              v-for="organ in organs"
              :key="organ"
              type="button"
              @click="triggerAlarm(organ, selectedLevel)"
            >
              {{ organLabel(organ) }}
            </button>
          </div>
          <div class="human-demo__toolbar human-demo__toolbar--levels">
            <button
              v-for="level in levels"
              :key="level.value"
              :class="['human-demo__button', level.value, { active: selectedLevel === level.value }]"
              type="button"
              @click="selectedLevel = level.value"
            >
              {{ level.label }}
            </button>
          </div>
          <button class="human-demo__clear" type="button" @click="store.clearAll(patientMode ? selectedPatientId : undefined)">
            清空当前报警
          </button>
        </section>

        <section class="human-demo__panel">
          <div class="human-demo__panel-head">
            <strong>活动报警</strong>
            <span>{{ visibleAlarms.length }}</span>
          </div>
          <div v-if="!visibleAlarms.length" class="human-demo__empty">暂无器官报警</div>
          <article v-for="alarm in visibleAlarms" :key="`${alarm.patientId || 'all'}-${alarm.organ}`" class="human-demo__alarm">
            <span :class="['human-demo__dot', alarm.level]" />
            <div>
              <strong>{{ organLabel(alarm.organ) }} · {{ levelText(alarm.level) }}</strong>
              <p>{{ alarm.bed || '床位--' }} {{ alarm.patientName || alarm.patientId || '聚合视图' }} · {{ alarm.metric || '指标' }} {{ alarm.value ?? '--' }}</p>
            </div>
          </article>
        </section>

        <section class="human-demo__panel human-demo__event">
          {{ lastEvent || (ready ? '人体视图已就绪' : '正在初始化人体视图') }}
        </section>
      </section>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import HumanBody from '../components/HumanBody/index.vue'
import { ORGAN_MAP, organLabel } from '../components/HumanBody/constants/organMap'
import { useHumanBodyAlarmStore } from '../stores/humanBodyAlarmStore'
import type { HumanBodyAlarmLevel } from '../types/alarm'
import type { HumanBodyForceTier, OrganBusinessName } from '../types/organ'

const store = useHumanBodyAlarmStore()
function initialForceTier(): HumanBodyForceTier {
  if (typeof window === 'undefined') return '2d'
  const raw = new URLSearchParams(window.location.search).get('force')
  return raw === 'high' || raw === 'low' || raw === '2d' ? raw : '2d'
}

const forceTier = ref<HumanBodyForceTier>(initialForceTier())
const patientMode = ref(false)
const selectedPatientId = ref('demo-patient-001')
const selectedLevel = ref<HumanBodyAlarmLevel>('critical')
const autoFocus = ref(true)
const ready = ref(false)
const lastEvent = ref('')

const organs = Object.keys(ORGAN_MAP) as OrganBusinessName[]
const tierOptions: Array<{ value: HumanBodyForceTier; label: string }> = [
  { value: '2d', label: '2D' },
  { value: 'low', label: '低模 3D' },
  { value: 'high', label: '高模 3D' },
]
const levels: Array<{ value: HumanBodyAlarmLevel; label: string }> = [
  { value: 'critical', label: '危急' },
  { value: 'warning', label: '预警' },
  { value: 'info', label: '关注' },
]
const visibleAlarms = computed(() => patientMode.value ? store.getAlarmsByPatient(selectedPatientId.value) : store.getAggregatedAlarms())
const topAlarm = computed(() => visibleAlarms.value[0] || null)
const levelRows = computed(() => [
  { level: 'critical', label: '危急', count: visibleAlarms.value.filter(alarm => alarm.level === 'critical').length },
  { level: 'warning', label: '预警', count: visibleAlarms.value.filter(alarm => alarm.level === 'warning').length },
  { level: 'info', label: '关注', count: visibleAlarms.value.filter(alarm => alarm.level === 'info').length },
])
const demoDeptRows = [
  { dept: '综合 ICU', patientCount: 12 },
  { dept: '急诊 ICU', patientCount: 8 },
  { dept: '神外 ICU', patientCount: 6 },
]

function levelText(level: HumanBodyAlarmLevel) {
  return level === 'critical' ? '危急' : level === 'warning' ? '预警' : '关注'
}

function triggerAlarm(organ: OrganBusinessName, level: HumanBodyAlarmLevel) {
  store.setAlarm(organ, {
    level,
    metric: level === 'critical' ? 'MAP' : level === 'warning' ? 'SpO2' : 'HR',
    value: level === 'critical' ? 52 : level === 'warning' ? 88 : 112,
    patientId: patientMode.value ? selectedPatientId.value : `demo-${Math.floor(Math.random() * 4) + 1}`,
    patientName: patientMode.value ? '单患者演示' : '聚合患者',
    bed: patientMode.value ? '03' : `${Math.floor(Math.random() * 12) + 1}`,
    source: 'human_body_demo',
  })
}

function handleOrganClick(organ: OrganBusinessName, patientId?: string) {
  lastEvent.value = `点击器官：${organLabel(organ)}${patientId ? `，患者 ${patientId}` : ''}`
}
</script>

<style scoped>
.human-demo {
  min-height: 100vh;
  padding: 18px;
  background: #07111f;
  color: #e8f7ff;
}

.human-demo__header,
.human-demo__panel,
.human-demo__alarm {
  border: 1px solid rgba(128, 213, 255, 0.16);
  background: rgba(8, 22, 38, 0.86);
}

.human-demo__header {
  min-height: 72px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 14px 16px;
  border-radius: 8px;
}

.human-demo__kicker {
  color: #67e8f9;
  font-size: 12px;
  letter-spacing: .12em;
  text-transform: uppercase;
}

.human-demo h1 {
  margin: 4px 0 0;
  font-size: 24px;
}

.human-demo__layout {
  display: grid;
  gap: 14px;
  margin-top: 14px;
  padding: 14px;
  border-radius: 8px;
  border: 1px solid rgba(128, 213, 255, 0.16);
  background: rgba(8, 22, 38, 0.62);
}

.human-demo__top,
.human-demo__bottom {
  display: grid;
  gap: 14px;
}

.human-demo__top {
  grid-template-columns: 3fr 6fr 3fr;
  min-height: 58vh;
}

.human-demo__bottom {
  grid-template-columns: 360px minmax(0, 1fr) 280px;
}

.human-demo__stage {
  min-height: 420px;
  overflow: hidden;
  border-radius: 8px;
  border: 1px solid rgba(128, 213, 255, 0.16);
  background: rgba(8, 22, 38, 0.86);
}

.human-demo__panel {
  display: grid;
  gap: 12px;
}

.human-demo__panel {
  align-content: start;
  padding: 14px;
  border-radius: 8px;
}

.human-demo__panel-head,
.human-demo__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
}

.human-demo__button,
.human-demo__organ-grid button,
.human-demo__clear {
  min-height: 36px;
  border: 1px solid rgba(128, 213, 255, 0.18);
  border-radius: 6px;
  color: #dff7ff;
  background: rgba(17, 42, 68, 0.9);
  cursor: pointer;
}

.human-demo__button.active {
  border-color: #00e5ff;
  color: #00131a;
  background: #67e8f9;
}

.human-demo__button.critical.active { background: #ff6666; }
.human-demo__button.warning.active { background: #ffaa00; }
.human-demo__button.info.active { background: #ffee44; }

.human-demo__field {
  display: grid;
  gap: 6px;
  color: #9ccce0;
  font-size: 12px;
}

.human-demo__field input {
  min-height: 36px;
  padding: 0 10px;
  border: 1px solid rgba(128, 213, 255, 0.18);
  border-radius: 6px;
  color: #e8f7ff;
  background: rgba(2, 10, 18, 0.72);
}

.human-demo__organ-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.human-demo__clear {
  width: 100%;
}

.human-demo__focus-main {
  display: grid;
  gap: 10px;
  padding: 14px;
  border-radius: 10px;
  background: rgba(17, 42, 68, 0.9);
}

.human-demo__focus-main b {
  color: #67e8f9;
  font-size: 28px;
}

.human-demo__focus-main strong {
  color: #fff;
  font-size: 22px;
}

.human-demo__stat-row,
.human-demo__dept {
  display: grid;
  grid-template-columns: 14px 1fr auto;
  align-items: center;
  gap: 10px;
  min-height: 34px;
  padding: 8px 10px;
  border-radius: 8px;
  background: rgba(17, 42, 68, 0.72);
}

.human-demo__dept {
  grid-template-columns: 1fr auto;
  color: #9ccce0;
}

.human-demo__dept-list {
  display: grid;
  gap: 8px;
  margin-top: 4px;
}

.human-demo__alarm {
  display: grid;
  grid-template-columns: 14px minmax(0, 1fr);
  gap: 10px;
  padding: 10px;
  border-radius: 8px;
}

.human-demo__alarm p {
  margin: 4px 0 0;
  color: #98b9c9;
  font-size: 12px;
}

.human-demo__dot {
  width: 10px;
  height: 10px;
  margin-top: 4px;
  border-radius: 999px;
}

.human-demo__dot.critical { background: #ff2222; box-shadow: 0 0 12px #ff2222; }
.human-demo__dot.warning { background: #ffaa00; box-shadow: 0 0 12px #ffaa00; }
.human-demo__dot.info { background: #ffee44; box-shadow: 0 0 12px #ffee44; }

.human-demo__empty,
.human-demo__event {
  color: #98b9c9;
}

@media (max-width: 980px) {
  .human-demo__top,
  .human-demo__bottom {
    grid-template-columns: 1fr;
  }
}
</style>
