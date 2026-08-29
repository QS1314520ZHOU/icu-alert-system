<template>
  <div class="handover-overview">
    <!-- Header -->
    <header class="overview-header">
      <div class="header-left">
        <h1 class="page-title">智能交接班</h1>
        <span class="dept-name">{{ deptName || '全院' }}</span>
        <span v-if="currentShift" class="shift-badge">{{ currentShift.name }}</span>
      </div>
      <div class="header-right">
        <a-button type="primary" :loading="generating" @click="onGenerate">
          生成总结
        </a-button>
        <a-button @click="onRefresh">刷新</a-button>
      </div>
    </header>

    <!-- Stats cards -->
    <div class="stats-row" v-if="summary">
      <div class="stat-card">
        <div class="stat-value">{{ summary.patient_count }}</div>
        <div class="stat-label">在科患者</div>
      </div>
      <div class="stat-card stat-card--critical">
        <div class="stat-value">{{ summary.critical_patient_count }}</div>
        <div class="stat-label">危重患者</div>
      </div>
      <div class="stat-card stat-card--warning">
        <div class="stat-value">{{ summary.draft_patient_count }}</div>
        <div class="stat-label">未完成交班</div>
      </div>
      <div class="stat-card stat-card--info">
        <div class="stat-value">{{ summary.submitted_patient_count }}</div>
        <div class="stat-label">待签收</div>
      </div>
      <div class="stat-card stat-card--alert">
        <div class="stat-value">{{ summary.unclosed_alert_count }}</div>
        <div class="stat-label">未闭环告警</div>
      </div>
      <div class="stat-card stat-card--task">
        <div class="stat-value">{{ summary.overdue_task_count }}</div>
        <div class="stat-label">逾期任务</div>
      </div>
    </div>

    <!-- Summary text -->
    <a-card v-if="summary?.deterministic_summary" class="summary-card" title="整体交班摘要">
      <p class="summary-text">{{ summary.deterministic_summary }}</p>
      <p v-if="summary.ai_summary" class="ai-summary-text">{{ summary.ai_summary }}</p>
      <div class="summary-meta">
        数据截止：{{ summary.data_end }} | 生成时间：{{ summary.created_at }}
      </div>
    </a-card>

    <!-- Priority items -->
    <a-card v-if="summary?.priority_items?.length" class="priority-card" title="重点患者">
      <a-table
        :data-source="summary.priority_items"
        :columns="priorityColumns"
        size="small"
        :pagination="false"
        row-key="patient_id"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'severity'">
            <a-tag :color="severityColor(record.severity)">{{ record.severity }}</a-tag>
          </template>
          <template v-if="column.key === 'action'">
            <a @click="goToPatient(record.patient_id)">查看ISBAR</a>
          </template>
        </template>
      </a-table>
    </a-card>

    <!-- Life support summary -->
    <div class="life-support-row" v-if="summary">
      <a-card class="ls-card" title="生命支持统计" size="small">
        <div class="ls-grid">
          <div class="ls-item">
            <span class="ls-value">{{ summary.ventilator_patient_count }}</span>
            <span class="ls-label">呼吸机</span>
          </div>
          <div class="ls-item">
            <span class="ls-value">{{ summary.vasoactive_patient_count }}</span>
            <span class="ls-label">血管活性药</span>
          </div>
          <div class="ls-item">
            <span class="ls-value">{{ summary.crrt_patient_count }}</span>
            <span class="ls-label">CRRT</span>
          </div>
          <div class="ls-item">
            <span class="ls-value">{{ summary.isolation_patient_count }}</span>
            <span class="ls-label">隔离</span>
          </div>
          <div class="ls-item">
            <span class="ls-value">{{ summary.high_risk_line_count }}</span>
            <span class="ls-label">高危管路</span>
          </div>
        </div>
      </a-card>
    </div>

    <!-- Empty state -->
    <a-empty v-if="!loading && !summary" description="暂无交班总结数据，请点击生成" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Card as ACard, Button as AButton, Table as ATable, Tag as ATag, Empty as AEmpty, message } from 'ant-design-vue'
import { useAuthStore } from '../../stores/auth'
import api from '../../api'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const loading = ref(false)
const generating = ref(false)
const summary = ref<any>(null)
const currentShift = ref<any>(null)

const deptCode = computed(() => authStore.deptCode || (route.query.dept_code as string) || '')
const deptName = computed(() => authStore.dept || (route.query.dept as string) || '')

const priorityColumns = [
  { title: '床号', dataIndex: 'bed', key: 'bed', width: 80 },
  { title: '姓名', dataIndex: 'name', key: 'name', width: 100 },
  { title: '原因', dataIndex: 'reason', key: 'reason' },
  { title: '等级', key: 'severity', width: 80 },
  { title: '操作', key: 'action', width: 100 },
]

function severityColor(s: string) {
  if (s === 'critical') return 'red'
  if (s === 'high') return 'orange'
  return 'blue'
}

async function loadSummary() {
  loading.value = true
  try {
    const res = await api.get('/api/handover/shifts/current/summary', {
      params: { dept_code: deptCode.value }
    })
    summary.value = res.data?.summary || null
  } catch (e: any) {
    console.error('Failed to load summary:', e)
  } finally {
    loading.value = false
  }
}

async function loadCurrentShift() {
  try {
    const res = await api.get('/api/handover/shifts/current')
    currentShift.value = res.data || null
  } catch {}
}

async function onGenerate() {
  generating.value = true
  try {
    const res = await api.post('/api/handover/shifts/current/generate', null, {
      params: {
        dept_code: deptCode.value,
        operator: authStore.effectiveUserId || '',
      }
    })
    summary.value = res.data?.summary || null
    message.success('交班总结已生成')
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '生成失败')
  } finally {
    generating.value = false
  }
}

function onRefresh() {
  loadSummary()
  loadCurrentShift()
}

function goToPatient(patientId: string) {
  router.push({ name: 'handover-patient', params: { patientId } })
}

onMounted(() => {
  loadCurrentShift()
  loadSummary()
})
</script>

<style scoped>
.handover-overview {
  padding: 24px;
  max-width: 1400px;
  margin: 0 auto;
}

.overview-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.page-title {
  font-size: 20px;
  font-weight: 600;
  color: #17233D;
  margin: 0;
}

.dept-name {
  font-size: 14px;
  color: #5F6B7A;
}

.shift-badge {
  background: #E6F4FF;
  color: #1677FF;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
}

.stats-row {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 16px;
  margin-bottom: 24px;
}

.stat-card {
  background: #fff;
  border-radius: 8px;
  padding: 16px;
  text-align: center;
  border: 1px solid #DCE5EF;
}

.stat-value {
  font-size: 28px;
  font-weight: 600;
  color: #17233D;
}

.stat-label {
  font-size: 12px;
  color: #5F6B7A;
  margin-top: 4px;
}

.stat-card--critical .stat-value { color: #D92D20; }
.stat-card--warning .stat-value { color: #F79009; }
.stat-card--info .stat-value { color: #2E90FA; }
.stat-card--alert .stat-value { color: #D92D20; }
.stat-card--task .stat-value { color: #F79009; }

.summary-card, .priority-card, .life-support-row {
  margin-bottom: 16px;
}

.summary-text {
  font-size: 14px;
  line-height: 1.8;
  color: #17233D;
}

.ai-summary-text {
  font-size: 14px;
  line-height: 1.8;
  color: #6E5AE6;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed #DCE5EF;
}

.summary-meta {
  font-size: 12px;
  color: #8A94A6;
  margin-top: 12px;
}

.ls-grid {
  display: flex;
  gap: 24px;
}

.ls-item {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.ls-value {
  font-size: 24px;
  font-weight: 600;
  color: #17233D;
}

.ls-label {
  font-size: 12px;
  color: #5F6B7A;
}

@media (max-width: 768px) {
  .stats-row {
    grid-template-columns: repeat(2, 1fr);
  }
  .handover-overview {
    padding: 12px;
  }
}
</style>
