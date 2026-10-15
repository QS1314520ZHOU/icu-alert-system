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
          @click="ctx.openEvidence(ctx.firstPatientId(), 'nursing', { contextId: item.key, title: `护理漏项：${item.label}` })"
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
          <button type="button" class="nursing-action" @click="ctx.openEvidence(task.patient_id, 'nursing', { title: `${task.bed || ''}床 护理任务` })">证据</button>
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
          @click="ctx.openEvidence(item.patient_id, 'nursing', { title: `护理雷达：${item.displayTitle || item.title}` })"
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
  gap: 14px;
}
.task-section {
  padding: 16px 18px;
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border);
  background: var(--color-bg-surface);
}
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.section-label {
  font-size: var(--text-card-title);
  font-weight: var(--weight-semibold);
  color: var(--color-text-primary);
  padding: 3px 10px;
  border-radius: var(--radius-tag);
}
.section-label.warning { background: var(--color-warning-soft-bg); color: var(--color-warning); }
.section-label.danger { background: var(--color-critical-bg); color: var(--color-danger); }
.section-label.info { background: var(--color-primary-bg); color: var(--color-primary); }
.section-count { font-size: var(--text-body); color: var(--color-text-secondary); font-weight: var(--weight-semibold); font-variant-numeric: tabular-nums; }

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
  background: var(--color-bg-inset);
  overflow: hidden;
}
.completion-fill {
  height: 100%;
  border-radius: 999px;
  background: var(--color-success);
  transition: width .3s ease;
}
.completion-text {
  font-size: var(--text-caption);
  font-weight: var(--weight-bold);
  color: var(--color-success);
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
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
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  color: var(--color-text-primary);
  background: var(--color-bg-surface-secondary);
  cursor: pointer;
}
.omission-cell:hover { border-color: var(--color-primary-hover); }
.omission-cell i {
  width: 20px;
  height: 20px;
  display: grid;
  place-items: center;
  border-radius: var(--radius-tag);
  font-style: normal;
  font-weight: var(--weight-bold);
  font-size: var(--text-caption);
}
.omission-cell span { font-size: var(--text-caption); }
.omission-cell.is-ok i { color: var(--color-text-inverse); background: var(--color-success); }
.omission-cell.is-todo { border-color: var(--color-warning-soft-border); background: var(--color-warning-soft-bg); }
.omission-cell.is-todo i { color: var(--color-text-inverse); background: var(--color-warning); }

.nursing-list { display: grid; gap: 8px; }
.nursing-row {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  padding: 12px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-bg-surface-secondary);
}
.nursing-info { flex: 1; min-width: 0; }
.nursing-info strong { display: block; color: var(--color-text-primary); font-size: var(--text-body); }
.nursing-info p { margin: 4px 0 0; color: var(--color-text-secondary); font-size: var(--text-caption); line-height: 1.4; }
.nursing-action {
  flex: 0 0 auto;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: 5px 10px;
  font-size: var(--text-caption);
  font-weight: var(--weight-bold);
  color: var(--color-primary);
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
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-bg-surface-secondary);
  color: var(--color-text-primary);
  cursor: pointer;
  text-align: left;
}
.radar-row:hover { border-color: var(--color-primary-hover); }
.radar-row strong { font-size: var(--text-body); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.radar-row span { font-size: var(--text-caption); color: var(--color-primary); font-weight: var(--weight-bold); white-space: nowrap; }

.empty-hint {
  padding: 24px;
  text-align: center;
  color: var(--color-text-secondary);
  font-size: var(--text-body);
}

@media (max-width: 1024px) {
  .omission-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
</style>
