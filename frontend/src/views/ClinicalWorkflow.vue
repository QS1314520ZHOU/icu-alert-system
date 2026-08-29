<template>
  <div class="clinical-workflow">
    <!-- 紧凑头部 -->
    <header class="cw-header">
      <div class="cw-header-left">
        <h1>{{ ctx.home.value?.title || '临床工作台' }}</h1>
        <span class="cw-role-tag">{{ ctx.roleLabel.value }}</span>
        <span class="cw-scope">{{ ctx.scopeLabel.value }}</span>
      </div>
      <div class="cw-header-right">
        <span class="cw-account">{{ ctx.accountLabel.value }}</span>
        <a-button size="small" :loading="ctx.loading.value" @click="ctx.loadHome()">刷新</a-button>
      </div>
    </header>

    <a-alert
      v-if="!ctx.loading.value && ctx.home.value?.account && ctx.home.value.account.found === false && ctx.routeUserName.value"
      class="soft-alert"
      type="warning"
      show-icon
      message="未匹配到账号，已按默认视角展示。"
    />

    <!-- 未闭环任务条 -->
    <div v-if="ctx.openTaskItems.value.length" class="open-task-strip">
      <span class="strip-label">待办 {{ ctx.openTaskTotal.value }}项</span>
      <div class="strip-chips">
        <button
          v-for="task in ctx.openTaskItems.value.slice(0, 5)"
          :key="task.task_id"
          type="button"
          class="strip-chip"
          @click="ctx.openExistingTask(task)"
        >
          <b>{{ task.bed_label || task.bed || '--' }}床</b>
          <span>{{ ctx.shortTaskText(task.title || '待处理', 16) }}</span>
        </button>
      </div>
    </div>

    <!-- Tab 导航 -->
    <nav class="cw-tabs">
      <button
        v-for="tab in visibleTabs"
        :key="tab.key"
        type="button"
        :class="['cw-tab', { active: activeTab === tab.key }]"
        @click="activeTab = tab.key"
      >{{ tab.label }}</button>
    </nav>

    <!-- Tab 内容 -->
    <div class="cw-content">
      <TodayTasksView v-if="activeTab === 'today'" :ctx="ctx" />
      <OrderClosureView v-if="activeTab === 'order'" :ctx="ctx" />
      <NursingTasksView v-if="activeTab === 'nursing'" :ctx="ctx" />
      <SpecialTreatmentsView v-if="activeTab === 'special'" :ctx="ctx" />
      <DirectorDashboardView v-if="activeTab === 'director'" :ctx="ctx" />
    </div>

    <!-- 共享抽屉：事件链/交班摘要 -->
    <a-drawer v-model:open="ctx.storyOpen.value" width="720px" title="患者事件链 / 交班摘要" class="story-drawer">
      <a-spin :spinning="ctx.storyLoading.value">
        <div v-if="ctx.featureDetail.value" class="feature-detail-panel">
          <div class="feature-detail-head">
            <span>{{ ctx.featureDetail.value.owner || '临床任务' }}</span>
            <strong>{{ ctx.featureDetail.value.title }}</strong>
          </div>
          <p>{{ ctx.featureDetail.value.detail }}</p>
          <div class="feature-detail-checklist">
            <div v-for="line in ctx.featureDetail.value.checklist" :key="line">{{ line }}</div>
          </div>
          <button v-if="ctx.featureTaskId.value" type="button" class="task-close-btn" @click="ctx.closeCurrentFeatureTask()">完成任务</button>
        </div>
        <div v-if="ctx.handoffText.value" class="handoff-text">{{ ctx.dedupeHandoffLines(ctx.handoffText.value) }}</div>
        <div v-if="ctx.story.value?.summary" class="story-summary">{{ ctx.story.value.summary }}</div>
        <div v-if="!ctx.storyLoading.value && !ctx.handoffText.value && ctx.story.value && !ctx.storyClusters.value.length" class="story-empty">
          <strong>暂未形成事件簇</strong>
          <p>过去窗口内没有可聚类事件。</p>
        </div>
        <div v-if="!ctx.storyLoading.value && !ctx.story.value && !ctx.handoffText.value" class="story-empty">
          <strong>请选择患者查看事件链或交班摘要</strong>
        </div>
        <div class="story-list">
          <div v-for="cluster in ctx.storyClusters.value" :key="`${cluster.start_time}-${cluster.headline}`" class="story-cluster">
            <strong>{{ ctx.clinicalText(cluster.headline) || '临床事件簇' }}</strong>
            <p>{{ ctx.clinicalText(cluster.summary) }}</p>
          </div>
        </div>
      </a-spin>
    </a-drawer>

    <!-- 证据抽屉 -->
    <ClinicalEvidenceDrawer
      :open="ctx.evidenceDrawer.value.open"
      :patient-id="ctx.evidenceDrawer.value.patientId"
      :context-type="ctx.evidenceDrawer.value.contextType"
      :context-id="ctx.evidenceDrawer.value.contextId"
      :organ-system="ctx.evidenceDrawer.value.organSystem"
      :title="ctx.evidenceDrawer.value.title"
      include-ai
      @close="ctx.closeEvidence()"
    />
  </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  Alert as AAlert,
  Button as AButton,
  Drawer as ADrawer,
  Spin as ASpin,
} from 'ant-design-vue'
import { useClinicalWorkflow } from '../composables/useClinicalWorkflow'
import TodayTasksView from './clinical-workflow/TodayTasksView.vue'
import OrderClosureView from './clinical-workflow/OrderClosureView.vue'
import NursingTasksView from './clinical-workflow/NursingTasksView.vue'
import SpecialTreatmentsView from './clinical-workflow/SpecialTreatmentsView.vue'
import DirectorDashboardView from './clinical-workflow/DirectorDashboardView.vue'
import ClinicalEvidenceDrawer from '../components/evidence/ClinicalEvidenceDrawer.vue'

const ctx = useClinicalWorkflow()

const activeTab = ref('today')

const allTabs = [
  { key: 'today', label: '今日任务', roles: ['doctor', 'nurse', 'head_nurse', 'director'] },
  { key: 'order', label: '医嘱闭环', roles: ['doctor', 'director'] },
  { key: 'nursing', label: '护理任务', roles: ['nurse', 'head_nurse', 'director'] },
  { key: 'special', label: '专项治疗', roles: ['doctor', 'nurse', 'head_nurse', 'director'] },
  { key: 'director', label: '管理驾驶舱', roles: ['director', 'head_nurse'] },
]

const visibleTabs = computed(() => {
  const role = ctx.home.value?.role || 'doctor'
  return allTabs.filter(tab => tab.roles.includes(role))
})

onMounted(() => {
  void ctx.loadHome()
})
</script>

<style scoped>
.clinical-workflow {
  display: grid;
  gap: 14px;
  padding: 18px;
  font-family: var(--app-display-font);
}

/* ── 头部 ── */
.cw-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 18px;
  border-radius: var(--card-radius);
  border: 1px solid var(--color-border);
  background: var(--bg-surface);
}
.cw-header-left { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.cw-header-left h1 {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1.2;
}
.cw-role-tag {
  padding: 2px 8px;
  border-radius: var(--card-radius);
  font-size: 11px;
  font-weight: 700;
  color: var(--color-primary);
  background: var(--color-primary-bg);
}
.cw-scope {
  font-size: 12px;
  color: var(--text-secondary);
}
.cw-header-right { display: flex; align-items: center; gap: 10px; }
.cw-account { font-size: 13px; color: var(--text-primary); font-weight: 700; }

.soft-alert { border-radius: var(--card-radius); }

/* ── 待办条 ── */
.open-task-strip {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  border-radius: var(--card-radius);
  border: 1px solid var(--color-warning-bg);
  background: var(--bg-surface);
}
.strip-label {
  flex: 0 0 auto;
  font-size: 13px;
  font-weight: 700;
  color: var(--color-warning);
}
.strip-chips {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  scrollbar-width: none;
}
.strip-chips::-webkit-scrollbar { display: none; }
.strip-chip {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border: 1px solid rgba(253,230,138,.2);
  border-radius: var(--card-radius);
  background: rgba(14,116,144,.06);
  color: var(--text-primary);
  cursor: pointer;
  white-space: nowrap;
}
.strip-chip b { font-size: 12px; color: var(--accent); }
.strip-chip span { font-size: 12px; color: var(--text-secondary); }

/* ── Tab ── */
.cw-tabs {
  display: flex;
  gap: 4px;
  padding: 4px;
  border-radius: var(--card-radius);
  background: rgba(14,116,144,.08);
  overflow-x: auto;
  scrollbar-width: none;
}
.cw-tabs::-webkit-scrollbar { display: none; }
.cw-tab {
  padding: 8px 16px;
  border: 0;
  border-radius: var(--card-radius);
  background: transparent;
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  white-space: nowrap;
  transition: background .15s, color .15s;
}
.cw-tab:hover { color: var(--text-primary); background: rgba(14,116,144,.12); }
.cw-tab.active {
  color: var(--text-primary);
  background: var(--bg-surface);
  box-shadow: 0 1px 3px rgba(0,0,0,.12);
}

/* ── 内容 ── */
.cw-content { min-height: 400px; }

/* ── 抽屉 ── */
.feature-detail-panel {
  display: grid;
  gap: 12px;
  padding: 14px;
  margin-bottom: 12px;
  border-radius: var(--card-radius);
  border: 1px solid rgba(94,234,212,.22);
  background: rgba(8,31,49,.28);
}
.feature-detail-head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.feature-detail-head span {
  padding: 3px 8px;
  border-radius: var(--card-radius);
  color: var(--text-primary);
  background: rgba(14,116,144,.18);
  font-size: 11px;
  font-weight: 700;
}
.feature-detail-head strong { color: var(--text-primary); font-size: 16px; }
.feature-detail-panel p { margin: 0; color: var(--text-primary); line-height: 1.6; font-size: 13px; }
.feature-detail-checklist { display: grid; gap: 6px; }
.feature-detail-checklist div {
  position: relative;
  padding: 8px 10px 8px 24px;
  border-radius: var(--card-radius);
  color: var(--text-primary);
  background: rgba(14,116,144,.1);
  line-height: 1.45;
  font-size: 13px;
}
.feature-detail-checklist div::before {
  content: "";
  position: absolute;
  left: 10px;
  top: 14px;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent);
}
.task-close-btn {
  width: fit-content;
  margin-top: 4px;
  padding: 8px 14px;
  border: 1px solid rgba(52,211,153,.28);
  border-radius: var(--card-radius);
  color: var(--color-success);
  background: rgba(26,156,91,.1);
  cursor: pointer;
  font-weight: 700;
  font-size: 13px;
}
.handoff-text {
  white-space: pre-wrap;
  padding: 12px;
  border-radius: var(--card-radius);
  margin-bottom: 12px;
  color: var(--color-success);
  background: rgba(63,98,18,.14);
  font-size: 13px;
  line-height: 1.6;
}
.story-summary { color: var(--text-primary); margin-bottom: 12px; font-size: 13px; line-height: 1.6; }
.story-empty {
  padding: 20px;
  border-radius: var(--card-radius);
  border: 1px dashed var(--color-border);
  text-align: center;
}
.story-empty strong { color: var(--text-primary); font-size: 14px; }
.story-empty p { margin: 8px 0 0; color: var(--text-secondary); font-size: 13px; }
.story-list { display: grid; gap: 10px; }
.story-cluster {
  padding: 12px;
  border-radius: var(--card-radius);
  border: 1px solid var(--color-border);
  background: rgba(14,116,144,.06);
}
.story-cluster strong { color: var(--text-primary); font-size: 13px; }
.story-cluster p { margin: 6px 0 0; color: var(--text-secondary); font-size: 13px; }

/* ── 响应式 ── */
@media (max-width: 1024px) {
  .clinical-workflow { padding: 14px; }
  .cw-header { flex-direction: column; align-items: flex-start; gap: 10px; }
  .cw-header-right { width: 100%; justify-content: space-between; }
  .open-task-strip { flex-direction: column; align-items: flex-start; gap: 8px; }
}
@media (max-width: 768px) {
  .clinical-workflow { padding: 12px; gap: 10px; }
  .cw-header-left h1 { font-size: 18px; }
  .cw-tab { padding: 6px 12px; font-size: 12px; }
}
</style>
