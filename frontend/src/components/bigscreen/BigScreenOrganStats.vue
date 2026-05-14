<template>
  <aside class="organ-stats">
    <section class="organ-stats__block">
      <div class="organ-stats__head">
        <span>报警等级统计</span>
        <b>{{ total }}</b>
      </div>
      <div class="organ-stats__levels">
        <div v-for="item in levels" :key="item.key" class="organ-stats__level">
          <span :class="['organ-stats__dot', `organ-stats__dot--${item.key}`]" />
          <span>{{ item.label }}</span>
          <strong>{{ item.count }}</strong>
        </div>
      </div>
    </section>

    <section class="organ-stats__block">
      <div class="organ-stats__head">
        <span>科室分布</span>
        <b>{{ deptRows.length }}</b>
      </div>
      <div class="organ-stats__dept-list">
        <div v-for="row in deptRows.slice(0, 5)" :key="row.dept" class="organ-stats__dept">
          <div class="organ-stats__dept-label">
            <span>{{ row.dept }}</span>
            <b>{{ row.patientCount }}床</b>
          </div>
          <div class="organ-stats__bar">
            <i :style="{ width: `${barWidth(row.patientCount)}%` }" />
          </div>
        </div>
      </div>
    </section>
  </aside>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { HumanBodyAlarmRecord } from '../../types/alarm'

const props = defineProps<{
  alarms: HumanBodyAlarmRecord[]
  deptRows: Array<{ dept: string; patientCount: number }>
}>()

const levels = computed(() => {
  const count = (key: string) => props.alarms.filter(alarm => alarm.level === key).length
  return [
    { key: 'critical', label: '危急', count: count('critical') },
    { key: 'warning', label: '预警', count: count('warning') },
    { key: 'info', label: '关注', count: count('info') },
  ]
})

const total = computed(() => levels.value.reduce((sum, item) => sum + item.count, 0))
const maxDept = computed(() => Math.max(1, ...props.deptRows.map(row => Number(row.patientCount || 0))))

function barWidth(value: number) {
  return Math.max(8, Math.round((Number(value || 0) / maxDept.value) * 100))
}
</script>

<style scoped>
.organ-stats {
  min-height: 100%;
  display: grid;
  grid-template-rows: auto 1fr;
  gap: 12px;
}

.organ-stats__block {
  padding: 14px;
  border-radius: 16px;
  border: 1px solid rgba(80, 199, 255, 0.14);
  background: linear-gradient(180deg, rgba(7, 20, 34, 0.96), rgba(4, 12, 22, 0.98));
}

.organ-stats__head,
.organ-stats__level,
.organ-stats__dept-label {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.organ-stats__head {
  color: #7ecce1;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: .08em;
  margin-bottom: 12px;
}

.organ-stats__head b {
  color: #effcff;
  font-size: 20px;
}

.organ-stats__levels,
.organ-stats__dept-list {
  display: grid;
  gap: 10px;
}

.organ-stats__level {
  min-height: 36px;
  padding: 8px 10px;
  border-radius: 10px;
  color: #cceef8;
  background: rgba(8, 28, 44, 0.78);
  border: 1px solid rgba(80, 199, 255, 0.08);
  font-size: 12px;
}

.organ-stats__level strong {
  color: #effcff;
  font-size: 18px;
}

.organ-stats__dot {
  width: 10px;
  height: 10px;
  border-radius: 999px;
  background: #ffee44;
  box-shadow: 0 0 12px currentColor;
}

.organ-stats__dot--critical { background: #ff2222; color: #ff2222; }
.organ-stats__dot--warning { background: #ffaa00; color: #ffaa00; }
.organ-stats__dot--info { background: #ffee44; color: #ffee44; }

.organ-stats__dept {
  display: grid;
  gap: 7px;
  color: #8fb8ca;
  font-size: 12px;
}

.organ-stats__dept-label b {
  color: #effcff;
}

.organ-stats__bar {
  height: 8px;
  overflow: hidden;
  border-radius: 999px;
  background: rgba(80, 199, 255, 0.12);
}

.organ-stats__bar i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #06b6d4, #67e8f9);
}
</style>
