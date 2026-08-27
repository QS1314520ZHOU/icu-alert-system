<template>
  <section class="shift-tasks">
    <div class="panel-head">
      <strong>本班任务</strong>
      <span>{{ tasks.length }} 条</span>
    </div>

    <!-- 状态筛选 -->
    <div class="task-filters">
      <button
        v-for="f in filters"
        :key="f.key"
        :class="['filter-chip', { active: activeFilter === f.key, 'has-count': f.count > 0 }]"
        @click="activeFilter = f.key"
      >
        {{ f.label }}
        <span v-if="f.count > 0" class="filter-count">{{ f.count }}</span>
      </button>
    </div>

    <!-- 任务列表 -->
    <div class="task-list">
      <article
        v-for="task in filteredTasks"
        :key="task.task_id"
        :class="['task-row', `is-${task.status}`]"
        @click="openDrawer(task)"
      >
        <div class="task-row__left">
          <i :class="['status-dot', statusDotClass(task.status)]"></i>
          <div class="task-row__info">
            <strong>{{ cleanTitle(task.title) }}</strong>
            <span>{{ displayBed(task.bed) }} {{ task.patient_name || '' }} · {{ fmt(task.due_at) }}</span>
          </div>
        </div>
        <span class="task-row__action">处理</span>
      </article>
      <div v-if="!filteredTasks.length" class="empty-hint">
        {{ activeFilter === 'all' ? '本班暂无任务' : '该状态下暂无任务' }}
      </div>
    </div>

    <!-- 任务操作抽屉 -->
    <Teleport to="body">
      <div v-if="drawerTask" class="drawer-mask" @click.self="closeDrawer">
        <div class="drawer-panel">
          <div class="drawer-head">
            <strong>{{ cleanTitle(drawerTask.title) }}</strong>
            <button class="drawer-close" @click="closeDrawer">✕</button>
          </div>
          <div class="drawer-body">
            <div class="drawer-meta">
              <span>{{ displayBed(drawerTask.bed) }} {{ drawerTask.patient_name || '' }}</span>
              <span>截止 {{ fmt(drawerTask.due_at) }}</span>
              <span :class="['drawer-status', `is-${drawerTask.status}`]">{{ statusLabel(drawerTask.status) }}</span>
            </div>
            <p v-if="drawerTask.description" class="drawer-desc">{{ drawerTask.description }}</p>
          </div>
          <div class="drawer-actions">
            <button class="action-btn primary" @click="handleAction('executed')">
              ✓ 执行
            </button>
            <button class="action-btn" @click="handleAction('delay_15m')">
              ⏱ 推迟15分钟
            </button>
            <button class="action-btn" @click="handleAction('handover')">
              ↗ 转交
            </button>
            <button class="action-btn subtle" @click="handleAction('not_applicable')">
              不适用
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'

interface Task {
  task_id: string
  patient_id: string
  title: string
  bed?: string
  patient_name?: string
  due_at?: string
  status: string
  description?: string
}

const props = defineProps<{
  tasks: Task[]
  displayBed: (v: any) => string
  fmt: (v: any) => string
}>()

const emit = defineEmits<{
  execute: [task: Task, action: string]
}>()

const activeFilter = ref('all')
const drawerTask = ref<Task | null>(null)

const PRIORITY_ORDER: Record<string, number> = { overdue: 0, due: 1, soon: 2, future: 3, done: 4 }

const sortedTasks = computed(() =>
  [...props.tasks].sort((a, b) => {
    const sa = PRIORITY_ORDER[a.status] ?? 3
    const sb = PRIORITY_ORDER[b.status] ?? 3
    if (sa !== sb) return sa - sb
    const da = new Date(a.due_at || 0).getTime()
    const db = new Date(b.due_at || 0).getTime()
    return da - db
  })
)

const filters = computed(() => [
  { key: 'all', label: '全部', count: props.tasks.length },
  { key: 'overdue', label: '逾期', count: props.tasks.filter(t => t.status === 'overdue').length },
  { key: 'due', label: '到点', count: props.tasks.filter(t => t.status === 'due').length },
  { key: 'soon', label: '临近', count: props.tasks.filter(t => t.status === 'soon').length },
])

const filteredTasks = computed(() => {
  if (activeFilter.value === 'all') return sortedTasks.value
  return sortedTasks.value.filter(t => t.status === activeFilter.value)
})

function cleanTitle(value: any) {
  return String(value || '')
    .replace(/PRE-DELIRIC近似/g, '谵妄风险')
    .replace(/[()（）]/g, '')
    .trim() || '待处理任务'
}

function statusDotClass(status: string) {
  if (status === 'overdue') return 'is-overdue'
  if (status === 'due') return 'is-due'
  if (status === 'soon') return 'is-soon'
  if (status === 'done') return 'is-done'
  return 'is-future'
}

function statusLabel(status: string) {
  const map: Record<string, string> = { overdue: '逾期', due: '到点', soon: '临近', future: '待执行', done: '已完成' }
  return map[status] || status
}

function openDrawer(task: Task) {
  drawerTask.value = task
}

function closeDrawer() {
  drawerTask.value = null
}

function handleAction(action: string) {
  if (drawerTask.value) {
    emit('execute', drawerTask.value, action)
    closeDrawer()
  }
}
</script>

<style scoped>
.shift-tasks {
  display: grid;
  gap: 10px;
  padding: var(--card-padding, 16px);
  border: 1px solid var(--color-border, #E3E7EC);
  border-radius: var(--radius-lg, 8px);
  background: var(--color-bg-surface, #fff);
}

.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}

.panel-head strong {
  font-size: var(--text-card-title, 14px);
  font-weight: var(--text-card-title-weight, 650);
  color: var(--color-text-primary, #18212B);
}

.panel-head span {
  font-size: var(--text-caption, 12px);
  color: var(--color-text-secondary, #667085);
}

/* 筛选 */
.task-filters {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.filter-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 28px;
  padding: 0 10px;
  border: 1px solid var(--color-border, #E3E7EC);
  border-radius: var(--radius-tag, 4px);
  background: transparent;
  color: var(--color-text-secondary, #667085);
  font-size: var(--text-caption, 12px);
  cursor: pointer;
  transition: all 0.15s;
}

.filter-chip:hover {
  border-color: var(--color-primary, #2563EB);
  color: var(--color-primary, #2563EB);
}

.filter-chip.active {
  background: var(--color-primary-bg, rgba(37, 99, 235, 0.08));
  border-color: var(--color-primary, #2563EB);
  color: var(--color-primary, #2563EB);
  font-weight: 500;
}

.filter-count {
  min-width: 16px;
  height: 16px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0 4px;
  border-radius: 8px;
  background: var(--color-bg-surface-secondary, #F1F3F5);
  font-size: 10px;
  font-weight: 600;
}

.filter-chip.active .filter-count {
  background: rgba(37, 99, 235, 0.15);
}

/* 任务列表 */
.task-list {
  display: grid;
  gap: 1px;
}

.task-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border-radius: var(--radius-md, 6px);
  cursor: pointer;
  transition: background 0.15s;
}

.task-row:hover {
  background: var(--color-bg-surface-secondary, #F1F3F5);
}

.task-row__left {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  flex: 1;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.status-dot.is-overdue { background: var(--color-danger, #D92D20); }
.status-dot.is-due { background: var(--color-warning, #B54708); }
.status-dot.is-soon { background: var(--color-primary, #2563EB); }
.status-dot.is-future { background: var(--color-border, #E3E7EC); }
.status-dot.is-done { background: var(--color-success, #16845B); }

.task-row__info {
  min-width: 0;
  display: grid;
  gap: 2px;
}

.task-row__info strong {
  font-size: var(--text-body, 14px);
  font-weight: 500;
  color: var(--color-text-primary, #18212B);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.task-row__info span {
  font-size: var(--text-caption, 12px);
  color: var(--color-text-secondary, #667085);
}

.task-row__action {
  font-size: var(--text-caption, 12px);
  color: var(--color-primary, #2563EB);
  flex-shrink: 0;
}

.task-row.is-overdue .task-row__info strong { color: var(--color-danger, #D92D20); }
.task-row.is-overdue { background: var(--color-danger-bg, rgba(217, 45, 32, 0.04)); }
.task-row.is-done { opacity: 0.6; }

.empty-hint {
  padding: 20px;
  text-align: center;
  font-size: var(--text-caption, 12px);
  color: var(--color-text-secondary, #667085);
}

/* 抽屉 */
.drawer-mask {
  position: fixed;
  inset: 0;
  z-index: 300;
  background: rgba(0, 0, 0, 0.3);
  display: flex;
  justify-content: flex-end;
}

.drawer-panel {
  width: min(400px, 90vw);
  height: 100%;
  display: grid;
  grid-template-rows: auto 1fr auto;
  background: var(--color-bg-surface, #fff);
  box-shadow: var(--shadow-xl);
  overflow: auto;
}

.drawer-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--color-border, #E3E7EC);
}

.drawer-head strong {
  font-size: var(--text-section-title, 16px);
  font-weight: var(--text-section-title-weight, 650);
  color: var(--color-text-primary, #18212B);
}

.drawer-close {
  width: 32px;
  height: 32px;
  display: grid;
  place-items: center;
  border: none;
  background: transparent;
  color: var(--color-text-secondary, #667085);
  font-size: 16px;
  cursor: pointer;
  border-radius: var(--radius-md, 6px);
}

.drawer-close:hover {
  background: var(--color-bg-surface-secondary, #F1F3F5);
}

.drawer-body {
  padding: 20px;
  display: grid;
  gap: 16px;
  align-content: start;
}

.drawer-meta {
  display: grid;
  gap: 6px;
}

.drawer-meta span {
  font-size: var(--text-body, 14px);
  color: var(--color-text-secondary, #667085);
}

.drawer-status {
  display: inline-flex;
  width: fit-content;
  padding: 2px 8px;
  border-radius: var(--radius-tag, 4px);
  font-size: var(--text-caption, 12px);
  font-weight: 500;
}

.drawer-status.is-overdue { background: var(--color-danger-bg); color: var(--color-danger); }
.drawer-status.is-due { background: var(--color-warning-bg); color: var(--color-warning); }
.drawer-status.is-soon { background: var(--color-primary-bg); color: var(--color-primary); }
.drawer-status.is-future { background: var(--color-bg-surface-secondary); color: var(--color-text-secondary); }
.drawer-status.is-done { background: var(--color-success-bg); color: var(--color-success); }

.drawer-desc {
  font-size: var(--text-body, 14px);
  color: var(--color-text-primary, #18212B);
  line-height: var(--text-body-line-height, 1.5);
  margin: 0;
}

.drawer-actions {
  padding: 16px 20px;
  border-top: 1px solid var(--color-border, #E3E7EC);
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.action-btn {
  height: var(--button-height, 40px);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  border: 1px solid var(--color-border, #E3E7EC);
  border-radius: var(--radius-button, 6px);
  background: var(--color-bg-surface, #fff);
  color: var(--color-text-primary, #18212B);
  font-size: var(--text-body, 14px);
  cursor: pointer;
  transition: all 0.15s;
}

.action-btn:hover {
  border-color: var(--color-primary, #2563EB);
  color: var(--color-primary, #2563EB);
}

.action-btn.primary {
  background: var(--color-primary, #2563EB);
  border-color: var(--color-primary, #2563EB);
  color: #fff;
}

.action-btn.primary:hover {
  background: var(--color-primary-hover, #1D4ED8);
}

.action-btn.subtle {
  border-color: transparent;
  color: var(--color-text-secondary, #667085);
}

.action-btn.subtle:hover {
  background: var(--color-bg-surface-secondary, #F1F3F5);
  color: var(--color-text-primary, #18212B);
}
</style>
