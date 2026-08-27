<template>
  <div class="nursing-tasks">
    <!-- 护理漏项 -->
    <section class="task-section">
      <div class="section-header">
        <span class="section-label warning">护理漏项</span>
        <span class="section-count">{{ ctx.nursingTodoCount.value }}项待完成</span>
      </div>
      <div class="completion-bar">
        <div class="completion-track">
          <div class="completion-fill" :style="{ width: `${ctx.nursingCompletion.value.percent ?? 100}%` }" />
        </div>
        <span class="completion-text">闭环 {{ ctx.nursingCompletion.value.percent ?? 100 }}%</span>
      </div>
      <div v-if="ctx.nursingOmissions.value.length" class="omission-grid">
        <button
          v-for="item in ctx.nursingOmissions.value"
          :key="item.key"
          type="button"
          :class="['omission-cell', item.status === 'todo' ? 'is-todo' : 'is-ok']"
          @click="ctx.applySignalFilter(item.key)"
        >
          <i>{{ item.status === 'todo' ? '!' : '✓' }}</i>
          <span>{{ item.label }}</span>
        </button>
      </div>
      <div v-else class="empty-hint">暂无护理漏项数据</div>
    </section>

    <!-- 护理待办 -->
    <section class="task-section">
      <div class="section-header">
        <span class="section-label danger">护理高优先级待办</span>
        <span class="section-count">{{ ctx.nursingTasks.value.length }}项</span>
      </div>
      <div v-if="ctx.nursingTasks.value.length" class="nursing-list">
        <div
          v-for="task in ctx.nursingTasks.value.slice(0, 10)"
          :key="`${task.patient_id}-${task.task_type}-${task.title}`"
          class="nursing-row"
        >
          <div class="nursing-info">
            <strong>{{ task.bed || '--' }}床 {{ task.name || '' }} · {{ task.title }}</strong>
            <p>{{ task.detail }}</p>
          </div>
          <button type="button" class="nursing-action" @click="ctx.openStory(task.patient_id)">事件</button>
        </div>
      </div>
      <div v-else class="empty-hint">暂无护理高优先级待办</div>
    </section>

    <!-- 护士任务雷达 -->
    <section v-if="nursingRadar.length" class="task-section">
      <div class="section-header">
        <span class="section-label info">护士任务雷达</span>
        <span class="section-count">{{ nursingRadar.length }}项</span>
      </div>
      <div class="radar-list">
        <button
          v-for="item in nursingRadar.slice(0, 6)"
          :key="`radar-${item.patient_id}-${item.title}`"
          type="button"
          class="radar-row"
          @click="ctx.openStory(item.patient_id)"
        >
          <strong>{{ item.displayTitle || item.title }}</strong>
          <span>{{ item.action || '查看' }}</span>
        </button>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ ctx: ReturnType<typeof import('../../composables/useClinicalWorkflow').useClinicalWorkflow> }>()

const nursingRadar = computed(() => {
  const features = props.ctx.stickyFeatures.value || {}
  return (features.nursing_radar || []).slice(0, 6)
})
</script>

<style scoped>
.nursing-tasks {
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
.section-label.warning { background: rgba(232,144,28,.15); color: #E8901C; }
.section-label.danger { background: rgba(217,52,43,.15); color: #D9342B; }
.section-label.info { background: rgba(21,85,141,.15); color: #15558D; }
.section-count { font-size: 13px; color: var(--text-secondary); font-weight: 700; }

.completion-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}
.completion-track {
  flex: 1;
  height: 8px;
  border-radius: 999px;
  background: rgba(125,211,252,.12);
  overflow: hidden;
}
.completion-fill {
  height: 100%;
  border-radius: 999px;
  background: #1A9C5B;
  transition: width .3s ease;
}
.completion-text {
  font-size: 12px;
  font-weight: 700;
  color: #1A9C5B;
  white-space: nowrap;
}

.omission-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}
.omission-cell {
  min-height: 50px;
  display: grid;
  place-items: center;
  gap: 3px;
  border: 1px solid rgba(125,211,252,.12);
  border-radius: var(--card-radius);
  color: var(--text-primary);
  background: rgba(14,116,144,.06);
  cursor: pointer;
}
.omission-cell:hover { border-color: rgba(103,232,249,.32); }
.omission-cell i {
  width: 20px;
  height: 20px;
  display: grid;
  place-items: center;
  border-radius: var(--card-radius);
  font-style: normal;
  font-weight: 700;
  font-size: 12px;
}
.omission-cell span { font-size: 12px; }
.omission-cell.is-ok i { color: #052e24; background: #1A9C5B; }
.omission-cell.is-todo { border-color: rgba(251,191,36,.34); background: rgba(113,63,18,.2); }
.omission-cell.is-todo i { color: #451a03; background: #E8901C; }

.nursing-list { display: grid; gap: 8px; }
.nursing-row {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  padding: 12px;
  border: 1px solid rgba(125,211,252,.1);
  border-radius: var(--card-radius);
  background: rgba(14,116,144,.06);
}
.nursing-info { flex: 1; min-width: 0; }
.nursing-info strong { display: block; color: var(--text-primary); font-size: 13px; }
.nursing-info p { margin: 4px 0 0; color: var(--text-secondary); font-size: 12px; line-height: 1.4; }
.nursing-action {
  flex: 0 0 auto;
  border: 1px solid rgba(125,211,252,.24);
  border-radius: var(--card-radius);
  padding: 5px 10px;
  font-size: 12px;
  font-weight: 700;
  color: var(--accent);
  background: transparent;
  cursor: pointer;
}

.radar-list { display: grid; gap: 6px; }
.radar-row {
  width: 100%;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 12px;
  align-items: center;
  padding: 10px 12px;
  border: 1px solid rgba(125,211,252,.1);
  border-radius: var(--card-radius);
  background: rgba(14,116,144,.06);
  color: var(--text-primary);
  cursor: pointer;
  text-align: left;
}
.radar-row:hover { border-color: rgba(103,232,249,.32); }
.radar-row strong { font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.radar-row span { font-size: 12px; color: var(--accent); font-weight: 700; white-space: nowrap; }

.empty-hint {
  padding: 24px;
  text-align: center;
  color: var(--text-secondary);
  font-size: 13px;
}

@media (max-width: 1024px) {
  .omission-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
</style>
