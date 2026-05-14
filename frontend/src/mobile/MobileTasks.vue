<template>
  <div class="mobile-page">
    <section class="mobile-segment">
      <button v-for="item in filters" :key="item.key" type="button" :class="{ active: filter === item.key }" @click="filter = item.key">
        {{ item.label }}
      </button>
    </section>
    <section class="mobile-card">
      <div class="mobile-section-head"><h2>任务闭环</h2><button type="button" @click="loadTasks">刷新</button></div>
      <article v-for="task in filteredTasks" :key="task.id" class="mobile-task-card">
        <div>
          <strong>{{ task.title }}</strong>
          <p>{{ task.desc }}</p>
          <div class="mobile-chip-row"><span>{{ task.kind }}</span><span>{{ task.patient }}</span><span>{{ task.status }}</span></div>
        </div>
        <button type="button" :disabled="closingId === task.id" @click="closeTask(task)">完成</button>
      </article>
      <div v-if="loading" class="mobile-empty">正在加载...</div>
      <div v-if="!loading && !filteredTasks.length" class="mobile-empty">暂无任务</div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { closeClinicalTask, getClinicalRoleHome, getPatients, postNurseTaskExecute } from '../api'
import { closeNutritionTask, getNutritionTasks } from '../api/nutrition'
import { closeRespiratoryWorklistTask, getRespiratoryWorklist } from '../api/respiratory'
import { useMobileShell } from '../composables/useMobileShell'
import { arrayFromResponse, firstText, patientIdOf, patientNameOf } from './mobileData'
import { MOBILE_ACTION_SOURCE } from './types'

type MobileTask = {
  id: string
  source: 'clinical' | 'nurse' | 'respiratory' | 'nutrition'
  patientId?: string
  title: string
  desc: string
  patient: string
  kind: string
  status: string
}

const shell = useMobileShell()
const loading = ref(false)
const closingId = ref('')
const tasks = ref<MobileTask[]>([])
const filter = ref('todo')
const filters = [
  { key: 'todo', label: '待处理' },
  { key: 'done', label: '已完成' },
  { key: 'all', label: '全部' },
]
const filteredTasks = computed(() => {
  if (filter.value === 'all') return tasks.value
  if (filter.value === 'done') return tasks.value.filter((task) => task.status.includes('完成') || task.status.includes('closed'))
  return tasks.value.filter((task) => !task.status.includes('完成') && !task.status.includes('closed'))
})

function scopeParams() {
  const params: Record<string, any> = { patient_scope: 'in_dept' }
  if (shell.deptCode.value) params.dept_code = shell.deptCode.value
  else if (shell.deptLabel.value && shell.deptLabel.value !== '全院') params.dept = shell.deptLabel.value
  return params
}

function normalizeTask(row: any, source: MobileTask['source']): MobileTask {
  const patient = row?.patient || row
  const id = firstText(row, ['task_id', 'id', '_id', 'alert_id'], `${source}-${Math.random().toString(36).slice(2)}`)
  return {
    id,
    source,
    patientId: patientIdOf(row) || patientIdOf(patient),
    title: firstText(row, ['title', 'name', 'task_name', 'action'], source === 'nutrition' ? '营养任务' : source === 'respiratory' ? '呼吸任务' : '临床任务'),
    desc: firstText(row, ['description', 'summary', 'note', 'reason'], '等待床旁闭环'),
    patient: `${firstText(patient, ['bed_no', 'bed', 'bedNo'], '--')} ${patientNameOf(patient)}`,
    kind: ({ clinical: '临床', nurse: '护理', respiratory: '呼吸', nutrition: '营养' } as Record<string, string>)[source] || source,
    status: firstText(row, ['status', 'state'], '待处理'),
  }
}

async function loadTasks() {
  loading.value = true
  try {
    const scope = scopeParams()
    const collected: MobileTask[] = []
    const [roleRes, respRes, patientRes] = await Promise.allSettled([
      getClinicalRoleHome({ userName: shell.actor.value, role: shell.role.value, ...scope }),
      getRespiratoryWorklist(scope),
      getPatients(scope),
    ])
    if (roleRes.status === 'fulfilled') {
      const data = roleRes.value.data || {}
      const rows = [
        ...arrayFromResponse(data.tasks, ['items']),
        ...arrayFromResponse(data.todo, ['items']),
        ...arrayFromResponse(data.work_items, ['items']),
      ]
      rows.forEach((row: any) => collected.push(normalizeTask(row, firstText(row, ['source', 'kind']).includes('nurse') ? 'nurse' : 'clinical')))
    }
    if (respRes.status === 'fulfilled') {
      arrayFromResponse(respRes.value.data, ['tasks', 'worklist', 'items']).forEach((row: any) => collected.push(normalizeTask(row, 'respiratory')))
    }
    if (patientRes.status === 'fulfilled') {
      const patientRows = arrayFromResponse(patientRes.value.data, ['patients']).slice(0, 12)
      const nutritionResults = await Promise.allSettled(patientRows.map((p: any) => getNutritionTasks(patientIdOf(p))))
      nutritionResults.forEach((res, idx) => {
        if (res.status !== 'fulfilled') return
        arrayFromResponse(res.value.data, ['tasks', 'items']).forEach((row: any) => collected.push(normalizeTask({ ...row, patient: patientRows[idx] }, 'nutrition')))
      })
    }
    tasks.value = collected
  } finally {
    loading.value = false
  }
}

async function closeTask(task: MobileTask) {
  closingId.value = task.id
  try {
    const payload = { actor: shell.actor.value, source: MOBILE_ACTION_SOURCE, note: '移动端闭环' }
    if (task.source === 'clinical') await closeClinicalTask(task.id, payload)
    else if (task.source === 'nurse') await postNurseTaskExecute(task.id, payload)
    else if (task.source === 'respiratory') await closeRespiratoryWorklistTask(task.id, payload)
    else if (task.source === 'nutrition') await closeNutritionTask(task.id, payload)
    tasks.value = tasks.value.map((item) => item.id === task.id ? { ...item, status: '已完成' } : item)
  } finally {
    closingId.value = ''
  }
}

function refreshFromShell() {
  void loadTasks()
}

watch(() => [shell.deptCode.value, shell.deptLabel.value], () => {
  tasks.value = []
  void loadTasks()
})

onMounted(() => {
  void shell.resolveIdentity().finally(() => loadTasks())
  window.addEventListener('mobile:refresh', refreshFromShell)
})

onUnmounted(() => {
  window.removeEventListener('mobile:refresh', refreshFromShell)
})
</script>
