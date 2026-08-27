<template>
  <div class="today-tasks">
    <!-- 高风险患者 -->
    <section class="task-section">
      <div class="section-header">
        <span class="section-label danger">高风险患者</span>
        <span class="section-count">{{ highRiskPatients.length }}人</span>
      </div>
      <div v-if="highRiskPatients.length" class="patient-list">
        <button
          v-for="p in highRiskPatients"
          :key="p.patient_id"
          type="button"
          class="patient-row"
          @click="ctx.openStory(p.patient_id)"
        >
          <span class="patient-bed">{{ p.bed || '--' }}床</span>
          <span class="patient-name">{{ p.name || '未知' }}</span>
          <span :class="['risk-badge', ctx.riskTone(p.risk_score)]">{{ p.risk_score || 0 }}</span>
          <span class="patient-alert">{{ ctx.shortTaskText(p.latest_alert?.name || p.latest_alert?.alert_type || '暂无', 20) }}</span>
        </button>
      </div>
      <div v-else class="empty-hint">暂无高风险患者</div>
    </section>

    <!-- 未闭环任务 -->
    <section class="task-section">
      <div class="section-header">
        <span class="section-label warning">未闭环任务</span>
        <span class="section-count">{{ unclosedTasks.length }}项</span>
      </div>
      <div v-if="unclosedTasks.length" class="task-list">
        <button
          v-for="t in unclosedTasks.slice(0, 8)"
          :key="`${t.patient_id}-${t.title}`"
          type="button"
          class="task-row"
          @click="ctx.openStory(t.patient_id)"
        >
          <span class="task-bed">{{ t.bed || '--' }}床</span>
          <span class="task-title">{{ ctx.shortTaskText(t.title || '待处理', 24) }}</span>
        </button>
      </div>
      <div v-else class="empty-hint">暂无未闭环任务</div>
    </section>

    <!-- 即将超时 -->
    <section v-if="timeoutTasks.length" class="task-section">
      <div class="section-header">
        <span class="section-label high">即将超时</span>
        <span class="section-count">{{ timeoutTasks.length }}项</span>
      </div>
      <div class="task-list">
        <button
          v-for="t in timeoutTasks.slice(0, 5)"
          :key="`timeout-${t.patient_id}-${t.title}`"
          type="button"
          class="task-row warn"
          @click="ctx.openStory(t.patient_id)"
        >
          <span class="task-bed">{{ t.bed || '--' }}床</span>
          <span class="task-title">{{ ctx.shortTaskText(t.title || '超时任务', 24) }}</span>
        </button>
      </div>
    </section>

    <!-- 最近重大事件 -->
    <section class="task-section">
      <div class="section-header">
        <span class="section-label info">最近重大事件</span>
        <span class="section-count">{{ recentEvents.length }}条</span>
      </div>
      <div v-if="recentEvents.length" class="event-list">
        <div
          v-for="e in recentEvents.slice(0, 6)"
          :key="`${e.patient_id}-${e.headline}`"
          class="event-row"
        >
          <span class="event-bed">{{ e.bed || '--' }}床</span>
          <span class="event-text">{{ ctx.clinicalText(e.headline || e.summary || '临床事件') }}</span>
          <button type="button" class="event-action" @click="ctx.openStory(e.patient_id)">查看</button>
        </div>
      </div>
      <div v-else class="empty-hint">暂无重大事件</div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ ctx: ReturnType<typeof import('../../composables/useClinicalWorkflow').useClinicalWorkflow> }>()

const highRiskPatients = computed(() => {
  const queue = props.ctx.filteredPriorityQueue.value || []
  return queue.filter((r: any) => Number(r.risk_score || 0) >= 4 || Number(r.critical_alerts || 0) > 0).slice(0, 10)
})

const unclosedTasks = computed(() => {
  const tasks = props.ctx.nursingTasks.value || []
  const gaps = props.ctx.doctorGaps.value || []
  const items = props.ctx.openTaskItems.value || []
  return [...items, ...tasks.filter((t: any) => t.tone === 'danger' || t.tone === 'warning'), ...gaps].slice(0, 12)
})

const timeoutTasks = computed(() => {
  const tasks = props.ctx.openTaskItems.value || []
  return tasks.filter((t: any) => {
    const due = t.due_at || t.deadline
    if (!due) return false
    const diff = new Date(due).getTime() - Date.now()
    return diff > 0 && diff < 2 * 60 * 60 * 1000
  })
})

const recentEvents = computed(() => {
  const queue = props.ctx.priorityQueue.value || []
  return queue.filter((r: any) => Number(r.critical_alerts || 0) > 0 || Number(r.risk_score || 0) >= 6)
    .map((r: any) => ({
      ...r,
      headline: r.latest_alert?.name || r.latest_alert?.alert_type || '高危事件',
      summary: r.latest_alert?.name || '',
    }))
    .slice(0, 8)
})
</script>

<style scoped>
.today-tasks {
  display: grid;
  gap: 16px;
}
.task-section {
  padding: 16px;
  border-radius: var(--card-radius);
  border: 1px solid rgba(125, 211, 252, .14);
  background: var(--bg-surface);
}
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.section-label {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary);
  padding: 3px 10px;
  border-radius: var(--card-radius);
}
.section-label.danger { background: rgba(217,52,43,.15); color: #D9342B; }
.section-label.warning { background: rgba(232,144,28,.15); color: #E8901C; }
.section-label.high { background: rgba(251,146,60,.15); color: #b96b12; }
.section-label.info { background: rgba(21,85,141,.15); color: #15558D; }
.section-count {
  font-size: 13px;
  color: var(--text-secondary);
  font-weight: 700;
}
.patient-list, .task-list, .event-list {
  display: grid;
  gap: 6px;
}
.patient-row {
  display: grid;
  grid-template-columns: 52px minmax(0, 1fr) 40px minmax(0, 1.2fr);
  gap: 10px;
  align-items: center;
  padding: 10px 12px;
  border: 1px solid rgba(125,211,252,.1);
  border-radius: var(--card-radius);
  background: rgba(14,116,144,.06);
  color: var(--text-primary);
  cursor: pointer;
  text-align: left;
}
.patient-row:hover { border-color: rgba(103,232,249,.32); }
.patient-bed { font-size: 13px; font-weight: 700; color: var(--accent); }
.patient-name { font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.risk-badge {
  display: inline-grid;
  place-items: center;
  min-width: 32px;
  height: 24px;
  border-radius: var(--card-radius);
  font-size: 12px;
  font-weight: 700;
}
.risk-high { background: rgba(127,29,29,.36); color: #f87171; }
.risk-mid { background: rgba(113,63,18,.32); color: #fbbf24; }
.risk-low { background: rgba(30,64,175,.24); color: #60a5fa; }
.patient-alert { font-size: 12px; color: var(--text-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.task-row {
  display: grid;
  grid-template-columns: 52px minmax(0, 1fr);
  gap: 10px;
  align-items: center;
  padding: 10px 12px;
  border: 1px solid rgba(125,211,252,.1);
  border-radius: var(--card-radius);
  background: rgba(14,116,144,.06);
  color: var(--text-primary);
  cursor: pointer;
  text-align: left;
}
.task-row:hover { border-color: rgba(103,232,249,.32); }
.task-row.warn { border-color: rgba(251,191,36,.24); }
.task-bed { font-size: 13px; font-weight: 700; color: var(--accent); }
.task-title { font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.event-row {
  display: grid;
  grid-template-columns: 52px minmax(0, 1fr) auto;
  gap: 10px;
  align-items: center;
  padding: 10px 12px;
  border: 1px solid rgba(125,211,252,.1);
  border-radius: var(--card-radius);
  background: rgba(14,116,144,.06);
}
.event-bed { font-size: 13px; font-weight: 700; color: var(--accent); }
.event-text { font-size: 13px; color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.event-action {
  border: 1px solid rgba(125,211,252,.24);
  border-radius: var(--card-radius);
  padding: 4px 10px;
  font-size: 12px;
  font-weight: 700;
  color: var(--accent);
  background: transparent;
  cursor: pointer;
}

.empty-hint {
  padding: 24px;
  text-align: center;
  color: var(--text-secondary);
  font-size: 13px;
}

@media (max-width: 1024px) {
  .patient-row { grid-template-columns: 44px minmax(0, 1fr) 36px; }
  .patient-alert { display: none; }
  .event-row { grid-template-columns: 44px minmax(0, 1fr) auto; }
}
</style>
