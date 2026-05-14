<template>
  <article :class="['organ-focus-card', `organ-focus-card--${topAlarm?.level || 'idle'}`, { pulse }]">
    <div class="organ-focus-card__head">
      <div>
        <div class="organ-focus-card__kicker">最高优先级器官报警</div>
        <h3>{{ topAlarm ? organLabel(topAlarm.organ) : '暂无器官报警' }}</h3>
      </div>
      <span :class="['organ-focus-card__level', `organ-focus-card__level--${topAlarm?.level || 'idle'}`]">
        {{ levelLabel(topAlarm?.level) }}
      </span>
    </div>

    <div v-if="topAlarm" class="organ-focus-card__body">
      <div class="organ-focus-card__patient">
        <strong>{{ topAlarm.bed || '--' }}床</strong>
        <span>{{ topAlarm.patientName || topAlarm.patientId || '聚合视图' }}</span>
      </div>
      <div class="organ-focus-card__metric">
        <span>{{ topAlarm.metric || '指标' }}</span>
        <b>{{ topAlarm.value ?? '--' }}</b>
      </div>
      <div class="organ-focus-card__meta">
        <span>来源 {{ topAlarm.source || 'alert_socket' }}</span>
        <span>持续 {{ durationText(topAlarm.timestamp) }}</span>
      </div>
    </div>

    <div v-else class="organ-focus-card__empty">
      WebSocket 推送 organ_alarm 后，这里会显示最需要处理的器官、患者和指标。
    </div>
  </article>
</template>

<script setup lang="ts">
import { organLabel } from '../HumanBody/constants/organMap'
import type { HumanBodyAlarmRecord } from '../../types/alarm'

defineProps<{
  topAlarm?: HumanBodyAlarmRecord | null
  pulse?: boolean
}>()

function levelLabel(level?: string) {
  if (level === 'critical') return '危急'
  if (level === 'warning') return '预警'
  if (level === 'info') return '关注'
  return '监测中'
}

function durationText(timestamp?: number) {
  if (!timestamp) return '--'
  const delta = Math.max(0, Date.now() - timestamp)
  const minutes = Math.floor(delta / 60000)
  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes}分钟`
  return `${Math.floor(minutes / 60)}小时${minutes % 60}分钟`
}
</script>

<style scoped>
.organ-focus-card {
  min-height: 100%;
  display: grid;
  align-content: start;
  gap: 16px;
  padding: 16px;
  border-radius: 16px;
  border: 1px solid rgba(80, 199, 255, 0.14);
  background: linear-gradient(180deg, rgba(7, 20, 34, 0.96), rgba(4, 12, 22, 0.98));
  box-shadow: inset 0 1px 0 rgba(145, 228, 255, 0.04), 0 14px 30px rgba(0, 0, 0, 0.22);
}

.organ-focus-card--critical {
  border-color: rgba(255, 34, 34, 0.42);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04), 0 0 28px rgba(255, 34, 34, 0.12);
}

.organ-focus-card.pulse {
  animation: organ-card-pulse 0.7s ease-in-out 3;
}

.organ-focus-card__head,
.organ-focus-card__patient,
.organ-focus-card__metric,
.organ-focus-card__meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.organ-focus-card__kicker {
  color: #6ea9bc;
  font-size: 10px;
  letter-spacing: .12em;
}

.organ-focus-card h3 {
  margin: 4px 0 0;
  color: #effcff;
  font-size: 24px;
}

.organ-focus-card__level {
  min-width: 54px;
  text-align: center;
  padding: 6px 10px;
  border-radius: 999px;
  color: #04111b;
  background: #67e8f9;
  font-size: 12px;
  font-weight: 800;
}

.organ-focus-card__level--critical { background: #ff5555; color: #fff; }
.organ-focus-card__level--warning { background: #ffaa00; }
.organ-focus-card__level--info { background: #ffee44; }
.organ-focus-card__level--idle { background: rgba(103, 232, 249, 0.16); color: #9ae8f7; }

.organ-focus-card__body {
  display: grid;
  gap: 12px;
}

.organ-focus-card__patient,
.organ-focus-card__metric {
  padding: 12px;
  border-radius: 12px;
  border: 1px solid rgba(80, 199, 255, 0.1);
  background: rgba(8, 28, 44, 0.78);
}

.organ-focus-card__patient strong,
.organ-focus-card__metric b {
  color: #effcff;
  font-size: 22px;
}

.organ-focus-card__patient span,
.organ-focus-card__metric span,
.organ-focus-card__meta,
.organ-focus-card__empty {
  color: #8fb8ca;
  font-size: 12px;
  line-height: 1.6;
}

.organ-focus-card__metric b {
  color: #67e8f9;
}

@keyframes organ-card-pulse {
  0%, 100% { transform: translateY(0); filter: brightness(1); }
  50% { transform: translateY(-2px); filter: brightness(1.28); }
}
</style>
