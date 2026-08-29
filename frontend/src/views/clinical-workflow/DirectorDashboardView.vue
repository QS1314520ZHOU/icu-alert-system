<template>
  <div class="director-dashboard">
    <!-- 昨夜事件 -->
    <section class="task-section">
      <div class="section-header">
        <span class="section-label high">昨夜事件</span>
        <span class="section-count">{{ nightEvents.length }}条</span>
      </div>
      <div v-if="nightEvents.length" class="event-list">
        <button
          v-for="e in nightEvents.slice(0, 8)"
          :key="`night-${e.patient_id}`"
          type="button"
          class="event-row"
          @click="ctx.openEvidence(e.patient_id, 'risk', { title: `${e.bed || ''}床 昨夜事件` })"
        >
          <span class="event-bed">{{ e.bed || '--' }}床</span>
          <span class="event-name">{{ e.name || '患者' }}</span>
          <span class="event-alert">{{ ctx.shortTaskText(e.latest_alert?.name || e.latest_alert?.alert_type || '高危事件', 20) }}</span>
        </button>
      </div>
      <div v-else class="empty-hint">昨夜暂无高危事件</div>
    </section>

    <!-- 未闭环 -->
    <section class="task-section">
      <div class="section-header">
        <span class="section-label danger">未闭环</span>
        <span class="section-count">{{ unclosedCount }}项</span>
      </div>
      <div class="metric-row">
        <div class="metric-item">
          <span>高危告警</span>
          <strong>{{ ctx.cards.value.find((c: any) => c.key === 'high_alerts')?.value || 0 }}</strong>
        </div>
        <div class="metric-item">
          <span>未确认</span>
          <strong>{{ unclosedCount }}</strong>
        </div>
        <div class="metric-item">
          <span>在科患者</span>
          <strong>{{ ctx.cards.value.find((c: any) => c.key === 'patients')?.value || 0 }}</strong>
        </div>
      </div>
    </section>

    <!-- 人力负荷 -->
    <section class="task-section">
      <div class="section-header">
        <span class="section-label info">人力负荷</span>
      </div>
      <div class="role-bars">
        <div v-for="row in roleBars" :key="row.key" class="role-bar-row">
          <span class="role-label">{{ row.label }}</span>
          <div class="role-track">
            <div class="role-fill" :style="{ width: `${row.percent}%`, background: row.color }" />
          </div>
          <span class="role-value">{{ row.value }}</span>
        </div>
      </div>
    </section>

    <!-- 规则噪声 -->
    <section class="task-section">
      <div class="section-header">
        <span class="section-label warning">规则噪声</span>
        <span class="section-count">{{ ctx.scannerReview.value.length }}条待复核</span>
      </div>
      <div v-if="ctx.scannerReview.value.length" class="scanner-list">
        <div
          v-for="row in ctx.scannerReview.value.slice(0, 5)"
          :key="row.scanner_name || row.name"
          class="scanner-row"
        >
          <strong>{{ row.scanner_name || row.name }}</strong>
          <span>PPV {{ ctx.pct(row.ppv) }} · 覆盖 {{ ctx.pct(row.override_rate) }}</span>
          <button type="button" class="scanner-detail-btn" @click.stop="ctx.openEvidence(ctx.firstPatientId(), 'rule_noise', { contextId: row.scanner_name || row.name, title: `规则噪声：${row.scanner_name || row.name}` })">详情</button>
        </div>
      </div>
      <div v-else class="empty-hint">暂无需人工复核的规则</div>
      <button type="button" class="link-btn" @click="ctx.router.push({ path: '/admin/scanner-health', query: ctx.route.query })">
        打开规则健康 →
      </button>
    </section>

    <!-- 典型病例 -->
    <section v-if="typicalCase" class="task-section">
      <div class="section-header">
        <span class="section-label stable">典型病例</span>
      </div>
      <button type="button" class="case-row" @click="ctx.openEvidence(typicalCase.patient_id, 'risk', { title: `${typicalCase.bed || ''}床 典型病例` })">
        <span class="case-bed">{{ typicalCase.bed || '--' }}床</span>
        <span class="case-name">{{ typicalCase.name || '患者' }}</span>
        <span :class="['risk-badge', ctx.riskTone(typicalCase.risk_score)]">风险 {{ typicalCase.risk_score || 0 }}</span>
      </button>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ ctx: ReturnType<typeof import('../../composables/useClinicalWorkflow').useClinicalWorkflow> }>()

const nightEvents = computed(() => {
  return props.ctx.priorityQueue.value.filter((r: any) => Number(r.risk_score || 0) > 0)
})

const unclosedCount = computed(() => {
  return Number(props.ctx.cards.value.find((c: any) => c.key === 'unacked')?.value || 0)
})

const typicalCase = computed(() => {
  return props.ctx.priorityQueue.value[0] || null
})

const roleBars = computed(() => {
  const colors: Record<string, string> = {
    nurse: 'var(--color-success)',
    doctor: '#60a5fa',
    head_nurse: 'var(--color-warning)',
    director: '#D9342B',
  }
  const source = props.ctx.roleDistribution.value.length
    ? props.ctx.roleDistribution.value
    : [
        { key: 'nurse', label: '护士', value: props.ctx.nursingTasks.value.length },
        { key: 'doctor', label: '医生', value: props.ctx.doctorGaps.value.length },
        { key: 'head_nurse', label: '护士长', value: props.ctx.qualityActions.value.length },
        { key: 'director', label: '主任', value: props.ctx.scannerReview.value.length },
      ]
  const max = Math.max(...source.map((r: any) => Number(r.value || 0)), 1)
  return source.map((row: any) => ({
    ...row,
    color: colors[row.key] || 'var(--color-primary)',
    percent: Math.max(8, Math.round((Number(row.value || 0) / max) * 100)),
  }))
})
</script>

<style scoped>
.director-dashboard {
  display: grid;
  gap: 16px;
}
.task-section {
  padding: 16px;
  border-radius: var(--card-radius);
  border: 1px solid var(--color-border);
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
.section-label.high { background: rgba(251,146,60,.15); color: #b96b12; }
.section-label.danger { background: rgba(217,52,43,.15); color: #D9342B; }
.section-label.info { background: rgba(21,85,141,.15); color: var(--color-primary); }
.section-label.warning { background: rgba(232,144,28,.15); color: var(--color-warning); }
.section-label.stable { background: rgba(26,156,91,.15); color: var(--color-success); }
.section-count { font-size: 13px; color: var(--text-secondary); font-weight: 700; }

.event-list { display: grid; gap: 6px; }
.event-row {
  display: grid;
  grid-template-columns: 52px 60px minmax(0, 1fr);
  gap: 10px;
  align-items: center;
  padding: 10px 12px;
  border: 1px solid var(--color-border);
  border-radius: var(--card-radius);
  background: var(--color-primary-bg);
  color: var(--text-primary);
  cursor: pointer;
  text-align: left;
}
.event-row:hover { border-color: rgba(103,232,249,.32); }
.event-bed { font-size: 13px; font-weight: 700; color: var(--accent); }
.event-name { font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.event-alert { font-size: 12px; color: var(--text-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.metric-row {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}
.metric-item {
  padding: 12px;
  border-radius: var(--card-radius);
  border: 1px solid var(--color-border);
  background: var(--color-primary-bg);
  text-align: center;
}
.metric-item span { display: block; font-size: 12px; color: var(--text-secondary); margin-bottom: 4px; }
.metric-item strong { display: block; font-size: 24px; color: var(--text-primary); font-weight: 700; }

.role-bars { display: grid; gap: 8px; }
.role-bar-row {
  display: grid;
  grid-template-columns: 56px minmax(0, 1fr) 32px;
  gap: 10px;
  align-items: center;
}
.role-label { font-size: 12px; color: var(--text-secondary); }
.role-track {
  height: 8px;
  border-radius: 999px;
  background: var(--color-border);
  overflow: hidden;
}
.role-fill { height: 100%; border-radius: 999px; transition: width .3s ease; }
.role-value { font-size: 12px; color: var(--text-primary); font-weight: 700; text-align: right; }

.scanner-list { display: grid; gap: 6px; }
.scanner-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  border: 1px solid var(--color-border);
  border-radius: var(--card-radius);
  background: var(--color-primary-bg);
}
.scanner-row strong { font-size: 13px; color: var(--text-primary); }
.scanner-row span { font-size: 12px; color: var(--text-secondary); }
.scanner-detail-btn {
  padding: 2px 8px;
  border: 1px solid var(--color-border);
  border-radius: 4px;
  background: #fff;
  font-size: 11px;
  color: var(--color-primary);
  cursor: pointer;
  white-space: nowrap;
}
.scanner-detail-btn:hover { background: var(--color-primary-bg); }

.link-btn {
  display: block;
  width: fit-content;
  margin-top: 10px;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--accent);
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
}

.case-row {
  display: grid;
  grid-template-columns: 52px minmax(0, 1fr) auto;
  gap: 10px;
  align-items: center;
  padding: 12px;
  border: 1px solid var(--color-border);
  border-radius: var(--card-radius);
  background: var(--color-primary-bg);
  color: var(--text-primary);
  cursor: pointer;
  text-align: left;
  width: 100%;
}
.case-row:hover { border-color: rgba(103,232,249,.32); }
.case-bed { font-size: 13px; font-weight: 700; color: var(--accent); }
.case-name { font-size: 13px; }
.risk-badge {
  display: inline-grid;
  place-items: center;
  min-width: 56px;
  height: 24px;
  border-radius: var(--card-radius);
  font-size: 12px;
  font-weight: 700;
}
.risk-high { background: rgba(127,29,29,.36); color: #f87171; }
.risk-mid { background: rgba(113,63,18,.32); color: #fbbf24; }
.risk-low { background: rgba(30,64,175,.24); color: #60a5fa; }

.empty-hint {
  padding: 20px;
  text-align: center;
  color: var(--text-secondary);
  font-size: 13px;
}

@media (max-width: 1024px) {
  .event-row { grid-template-columns: 44px minmax(0, 1fr); }
  .event-name { display: none; }
}
</style>
