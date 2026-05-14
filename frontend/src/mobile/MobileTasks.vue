<template>
  <div class="mobile-page mobile-tasks-page">
    <section class="mobile-task-hero">
      <div>
        <span>今日床旁闭环</span>
        <h1>{{ todoCount }}</h1>
        <p>待处理任务</p>
      </div>
      <button type="button" @click="refreshAll">刷新</button>
    </section>

    <section class="mobile-task-switch">
      <button type="button" :class="{ active: view === 'tasks' }" @click="view = 'tasks'">任务</button>
      <button type="button" :class="{ active: view === 'bundles' }" @click="view = 'bundles'">Bundle</button>
    </section>

    <section v-if="view === 'tasks'" class="mobile-card mobile-task-panel">
      <div class="mobile-task-filter">
        <button v-for="item in filters" :key="item.key" type="button" :class="{ active: filter === item.key }" @click="filter = item.key">
          <b>{{ countFor(item.key) }}</b>
          <span>{{ item.label }}</span>
        </button>
      </div>
      <article v-for="task in filteredTasks" :key="task.id" class="mobile-task-row">
        <div :class="['mobile-task-priority', `prio-${task.priority}`]">{{ priorityLabel(task.priority) }}</div>
        <div>
          <strong>{{ task.title }}</strong>
          <p>{{ task.desc }}</p>
          <div class="mobile-chip-row">
            <span>{{ task.patient }}</span>
            <span>{{ task.kind }}</span>
            <span>{{ statusLabel(task.status) }}</span>
          </div>
        </div>
        <button v-if="!isDone(task)" type="button" :disabled="closingId === task.id" @click="closeTask(task)">完成</button>
      </article>
      <div v-if="loading && !tasks.length" class="mobile-skeleton-list"><i></i><i></i><i></i></div>
      <div v-if="!loading && !filteredTasks.length" class="mobile-empty">
        {{ filter === 'done' ? '今天还没有完成记录' : '当前没有待处理任务' }}
      </div>
    </section>

    <section v-else class="mobile-card mobile-task-panel">
      <div class="mobile-section-head"><h2>今日 Bundle</h2><button type="button" @click="loadBundles">刷新</button></div>
      <article v-for="bundle in bundles" :key="bundle.bundle_id" class="mobile-bundle-card">
        <div class="mobile-bundle-head">
          <div>
            <strong>{{ bundlePatient(bundle) }} · {{ bundle.title || bundle.bundle_type }}</strong>
            <p>完成度 {{ bundlePercent(bundle) }}%</p>
          </div>
          <span>{{ bundleDone(bundle) }}/{{ bundle.items?.length || 0 }}</span>
        </div>
        <div class="mobile-progress"><i :style="{ width: `${bundlePercent(bundle)}%` }"></i></div>
        <div class="mobile-bundle-brief">
          <span v-for="item in bundleMissingTop(bundle)" :key="item.key">{{ item.label }}</span>
          <span v-if="!bundleMissingTop(bundle).length">已完成全部项目</span>
        </div>
        <button type="button" class="mobile-bundle-toggle" @click="toggleBundleExpand(bundle.bundle_id)">
          {{ expandedBundles.has(bundle.bundle_id) ? '收起清单' : `展开 ${bundle.items?.length || 0} 项` }}
        </button>
        <button
          v-for="item in expandedBundles.has(bundle.bundle_id) ? bundle.items : []"
          :key="item.key"
          type="button"
          :class="['mobile-bundle-check', { checked: item.checked }]"
          :disabled="closingId === `${bundle.bundle_id}:${item.key}`"
          @click="toggleBundle(bundle, item, !item.checked)"
        >
          <span>{{ item.checked ? '✓' : '' }}</span>
          <b>{{ item.label }}</b>
        </button>
      </article>
      <div v-if="loading && !bundles.length" class="mobile-skeleton-list"><i></i><i></i><i></i></div>
      <div v-if="!loading && !bundles.length" class="mobile-empty">暂无 Bundle 清单</div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { closeClinicalTask, completeMobileReviewReminder, getMobileBundles, getMobileTasks, postMobileBundleCheck } from '../api'
import { useMobileShell } from '../composables/useMobileShell'
import { arrayFromResponse, firstText, labelText } from './mobileData'
import { mobileScopeKey, readMobileCache, writeMobileCache } from './mobileCache'
import { MOBILE_ACTION_SOURCE } from './types'

type MobileTask = {
  id: string
  patientId?: string
  title: string
  desc: string
  patient: string
  kind: string
  status: string
  priority: string
  source: string
}

const shell = useMobileShell()
const loading = ref(false)
const closingId = ref('')
const tasks = ref<MobileTask[]>([])
const bundles = ref<any[]>([])
const expandedBundles = ref<Set<string>>(new Set())
const view = ref<'tasks' | 'bundles'>('tasks')
const filter = ref('todo')
const filters = [
  { key: 'todo', label: '待处理' },
  { key: 'done', label: '已完成' },
  { key: 'all', label: '全部' },
]
const cacheKey = computed(() => `mobile_tasks:${mobileScopeKey(shell.deptCode.value, shell.deptLabel.value)}:${shell.actor.value}`)
const filteredTasks = computed(() => {
  if (filter.value === 'all') return tasks.value
  if (filter.value === 'done') return tasks.value.filter(isDone)
  return tasks.value.filter((task) => !isDone(task))
})
const todoCount = computed(() => tasks.value.filter((task) => !isDone(task)).length)

function scopeParams() {
  const params: Record<string, any> = {}
  if (shell.deptCode.value) params.dept_code = shell.deptCode.value
  else if (shell.deptLabel.value && shell.deptLabel.value !== '全院') params.dept = shell.deptLabel.value
  return params
}

function normalizeTask(row: any): MobileTask {
  const id = firstText(row, ['task_id', 'id', '_id', 'reminder_id'], `task-${Math.random().toString(36).slice(2)}`)
  const module = firstText(row, ['module', 'source', 'kind'], 'clinical')
  return {
    id,
    source: module,
    patientId: firstText(row, ['patient_id', 'patientId']),
    title: labelText(firstText(row, ['title', 'name', 'task_name', 'task_type'], '床旁任务')),
    desc: labelText(firstText(row, ['description', 'detail', 'summary', 'note', 'reason'], '等待床旁闭环')),
    patient: compactJoin([firstText(row, ['bed', 'bed_no', 'bedNo']) ? `${firstText(row, ['bed', 'bed_no', 'bedNo'])}床` : '', firstText(row, ['patient_name', 'name'])]) || '未关联患者',
    kind: kindLabel(module, firstText(row, ['task_type'])),
    status: firstText(row, ['status', 'state'], 'pending'),
    priority: firstText(row, ['priority', 'severity'], 'medium').toLowerCase(),
  }
}

function compactJoin(values: any[]) {
  return values.map((item) => String(item ?? '').trim()).filter(Boolean).join(' ')
}

function kindLabel(module: string, type: string) {
  const key = `${module} ${type}`.toLowerCase()
  if (key.includes('review')) return '复评'
  if (key.includes('bundle')) return 'Bundle'
  if (key.includes('order_stub')) return '医嘱草稿'
  if (key.includes('handoff') || key.includes('sbar')) return '交班'
  if (key.includes('respiratory')) return '呼吸'
  if (key.includes('nutrition')) return '营养'
  if (key.includes('nurse')) return '护理'
  return '临床'
}

function isDone(task: MobileTask) {
  const status = String(task.status || '').toLowerCase()
  return ['closed', 'completed', 'done', '已完成'].some((item) => status.includes(item))
}

function statusLabel(status: string) {
  const value = String(status || '').toLowerCase()
  if (['closed', 'completed', 'done'].some((item) => value.includes(item))) return '已完成'
  if (value.includes('pending') || value.includes('open')) return '待处理'
  return labelText(status, '待处理')
}

function priorityLabel(priority: string) {
  const value = String(priority || '').toLowerCase()
  if (value.includes('high') || value.includes('critical')) return '高'
  if (value.includes('low')) return '低'
  return '中'
}

function countFor(key: string) {
  if (key === 'all') return tasks.value.length
  if (key === 'done') return tasks.value.filter(isDone).length
  return todoCount.value
}

function restoreCachedTasks() {
  const cached = readMobileCache<MobileTask[]>(cacheKey.value, [])
  if (cached.length && !tasks.value.length) tasks.value = cached
}

async function loadTasks() {
  loading.value = true
  restoreCachedTasks()
  try {
    const res = await getMobileTasks({ ...scopeParams(), actor: shell.actor.value, status: 'all', limit: 160 })
    const rows = arrayFromResponse(res.data, ['tasks']).map(normalizeTask)
    tasks.value = rows
    writeMobileCache(cacheKey.value, rows.slice(0, 160))
  } finally {
    loading.value = false
  }
}

async function loadBundles() {
  loading.value = true
  try {
    const scope = scopeParams()
    const res = await getMobileBundles({ dept: scope.dept, dept_code: scope.dept_code })
    bundles.value = arrayFromResponse(res.data, ['bundles'])
  } finally {
    loading.value = false
  }
}

async function refreshAll() {
  await Promise.allSettled([loadTasks(), loadBundles()])
}

async function closeTask(task: MobileTask) {
  closingId.value = task.id
  try {
    const payload = { actor: shell.actor.value, source: MOBILE_ACTION_SOURCE, note: '移动端完成' }
    if (task.kind === '复评') await completeMobileReviewReminder(task.id, { ...payload, result: 'reviewed' })
    else await closeClinicalTask(task.id, payload)
    tasks.value = tasks.value.map((item) => (item.id === task.id ? { ...item, status: 'completed' } : item))
    writeMobileCache(cacheKey.value, tasks.value.slice(0, 160))
  } finally {
    closingId.value = ''
  }
}

function bundlePatient(bundle: any) {
  const bed = firstText(bundle.patient, ['bed', 'bed_no', 'bedNo'])
  const name = firstText(bundle.patient, ['name', 'patient_name'], '患者')
  return compactJoin([bed ? `${bed}床` : '', name])
}

function bundleDone(bundle: any) {
  return Array.isArray(bundle.items) ? bundle.items.filter((item: any) => item.checked).length : 0
}

function bundlePercent(bundle: any) {
  const total = Array.isArray(bundle.items) ? bundle.items.length : 0
  return total ? Math.round((bundleDone(bundle) / total) * 100) : 0
}

function bundleMissingTop(bundle: any) {
  const items = Array.isArray(bundle.items) ? bundle.items : []
  return items.filter((item: any) => !item.checked).slice(0, 2)
}

function toggleBundleExpand(id: string) {
  const next = new Set(expandedBundles.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  expandedBundles.value = next
}

async function toggleBundle(bundle: any, item: any, checked: boolean) {
  const id = `${bundle.bundle_id}:${item.key}`
  closingId.value = id
  try {
    await postMobileBundleCheck({
      actor: shell.actor.value,
      source: MOBILE_ACTION_SOURCE,
      patient_id: bundle.patient_id,
      bundle_type: bundle.bundle_type,
      item_key: item.key,
      item_label: item.label,
      checked,
    })
    bundles.value = bundles.value.map((row) => {
      if (row.bundle_id !== bundle.bundle_id) return row
      const items = row.items.map((entry: any) => (entry.key === item.key ? { ...entry, checked } : entry))
      return { ...row, items, completion_rate: items.length ? items.filter((entry: any) => entry.checked).length / items.length : 0 }
    })
  } finally {
    closingId.value = ''
  }
}

function refreshFromShell() {
  void refreshAll()
}

watch(() => [shell.deptCode.value, shell.deptLabel.value], () => {
  tasks.value = []
  bundles.value = []
  void refreshAll()
})

onMounted(() => {
  restoreCachedTasks()
  void shell.resolveIdentity().finally(refreshAll)
  window.addEventListener('mobile:refresh', refreshFromShell)
})

onUnmounted(() => {
  window.removeEventListener('mobile:refresh', refreshFromShell)
})
</script>
