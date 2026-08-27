<template>
  <a-card :bordered="false" class="mdt-step-card">
    <div class="step-card__head">
      <div>
        <span class="step-kicker">第二步</span>
        <h2>审阅专科意见</h2>
      </div>
      <div class="step-card__head-actions">
        <a-button :disabled="!syncableAiActions.length || isGeneratingAssessment" @click="$emit('sync-decisions')">
          同步 AI 动作 ({{ syncableAiActions.length }})
        </a-button>
        <a-button type="primary" @click="$emit('next')">进入决议确认</a-button>
      </div>
    </div>

    <!-- 总控结论 + 冲突焦点：一行两列 -->
    <section class="review-summary-row">
      <article class="review-summary-card">
        <span>总控结论</span>
        <strong>{{ mdtSeverityLabel }}</strong>
        <p>{{ metaSummary }}</p>
      </article>
      <article v-if="conflictRows.length" class="review-summary-card is-warning">
        <span>冲突焦点</span>
        <strong>{{ conflictRows.length }} 项冲突</strong>
        <p>{{ conflictRows[0]?.summary || '跨专科意见不一致' }}</p>
      </article>
    </section>

    <!-- 专科意见列表：紧凑卡片 -->
    <section class="specialist-compact-list">
      <button
        v-for="item in systemCards"
        :key="item.agent"
        type="button"
        :class="['specialist-compact', `priority-${item.priority || 'medium'}`]"
        @click="openSpecialistDrawer(item)"
      >
        <div class="specialist-compact__main">
          <strong>{{ item.label }}</strong>
          <span class="specialist-compact__summary">{{ shortSummary(item.summary) }}</span>
        </div>
        <div class="specialist-compact__meta">
          <span :class="['priority-tag', `priority-${item.priority || 'medium'}`]">{{ priorityLabel(item.priority) }}</span>
          <span v-if="hasConflict(item.agent)" class="conflict-tag">冲突</span>
          <span v-if="!item.hasData" class="no-data-tag">无数据</span>
        </div>
      </button>
    </section>

    <!-- AI 建议动作（精简） -->
    <section v-if="syncableAiActions.length" class="ai-actions-strip">
      <span class="ai-actions-label">AI 建议动作</span>
      <div class="ai-actions-chips">
        <span v-for="(action, idx) in syncableAiActions.slice(0, 4)" :key="idx" class="ai-action-chip">{{ shortSummary(action, 36) }}</span>
        <span v-if="syncableAiActions.length > 4" class="ai-action-chip is-more">+{{ syncableAiActions.length - 4 }} 条</span>
      </div>
    </section>

    <!-- 专科详情抽屉 -->
    <a-drawer
      :open="drawerVisible"
      :title="drawerTitle"
      width="480"
      placement="right"
      @close="drawerVisible = false"
    >
      <div v-if="drawerSpecialist" class="drawer-body">
        <section class="drawer-section">
          <span class="drawer-section-label">专科结论</span>
          <p>{{ drawerSpecialist.summary || '暂无结论' }}</p>
        </section>

        <section v-if="(drawerSpecialist.concerns || []).length" class="drawer-section">
          <span class="drawer-section-label">关注点</span>
          <ul>
            <li v-for="(c, i) in drawerSpecialist.concerns" :key="i">{{ c }}</li>
          </ul>
        </section>

        <section v-if="(drawerSpecialist.recommendations || []).length" class="drawer-section">
          <span class="drawer-section-label">专科建议</span>
          <ul>
            <li v-for="(r, i) in drawerSpecialist.recommendations" :key="i">{{ r }}</li>
          </ul>
        </section>

        <section v-if="(drawerSpecialist.evidence || []).length" class="drawer-section">
          <span class="drawer-section-label">证据线索</span>
          <div class="drawer-chips">
            <span v-for="(e, i) in drawerSpecialist.evidence" :key="i">{{ e }}</span>
          </div>
        </section>
      </div>
    </a-drawer>
  </a-card>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { Button as AButton, Card as ACard, Drawer as ADrawer } from 'ant-design-vue'

const props = defineProps<{
  metaSummary: string
  mdtSeverityLabel: string
  activeSystemLabel: string
  conflictRows: any[]
  specialistRows: any[]
  systemCards: any[]
  activeSpecialist: any
  syncableAiActions: string[]
  isGeneratingAssessment: boolean
}>()

defineEmits<{
  (event: 'select-specialist', agent: string): void
  (event: 'sync-decisions'): void
  (event: 'next'): void
}>()

void AButton
void ACard
void ADrawer

const drawerVisible = ref(false)
const drawerSpecialist = ref<any>(null)

const drawerTitle = computed(() => {
  if (!drawerSpecialist.value) return '专科详情'
  const labels: Record<string, string> = {
    hemodynamic_agent: '循环系统', respiratory_agent: '呼吸系统', infection_agent: '感染系统',
    renal_agent: '肾脏系统', neuro_agent: '神经系统', nutrition_agent: '营养代谢', pharmacy_agent: '药学安全',
  }
  return labels[drawerSpecialist.value.agent] || '专科详情'
})

function openSpecialistDrawer(item: any) {
  drawerSpecialist.value = item
  drawerVisible.value = true
}

function hasConflict(agent: string): boolean {
  return props.conflictRows.some((c: any) => Array.isArray(c.agents) && c.agents.includes(agent))
}

function shortSummary(text: any, max = 52): string {
  const s = String(text || '').replace(/\s+/g, ' ').trim()
  return s.length > max ? `${s.slice(0, max)}…` : s || '暂无'
}

function priorityLabel(priority: any): string {
  const key = String(priority || 'medium').toLowerCase()
  return ({ critical: '危急', high: '高', medium: '中', low: '低' } as Record<string, string>)[key] || '中'
}
</script>

<style scoped>
.mdt-step-card {
  border: 1px solid var(--border-color);
  border-radius: var(--card-radius);
  background: var(--bg-surface);
}
.step-card__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
}
.step-card__head-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}
.step-kicker {
  color: var(--brand);
  font-size: 12px;
  font-weight: 700;
}
h2 {
  margin: 4px 0 0;
  color: var(--text-primary);
  font-size: 18px;
}

/* 总控结论 + 冲突 */
.review-summary-row {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 12px;
  margin-top: 16px;
}
.review-summary-card {
  padding: 14px;
  border: 1px solid var(--border-color);
  border-radius: var(--card-radius);
  background: var(--bg-surface);
}
.review-summary-card span {
  display: block;
  color: var(--brand);
  font-size: 12px;
  font-weight: 700;
}
.review-summary-card strong {
  display: block;
  margin: 4px 0;
  color: var(--text-primary);
  font-size: 16px;
}
.review-summary-card p {
  margin: 0;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.6;
}
.review-summary-card.is-warning {
  border-color: rgba(245, 158, 11, 0.3);
}

/* 专科紧凑列表 */
.specialist-compact-list {
  display: grid;
  gap: 8px;
  margin-top: 16px;
}
.specialist-compact {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  border: 1px solid var(--border-color);
  border-radius: var(--card-radius);
  background: var(--bg-surface);
  cursor: pointer;
  text-align: left;
  transition: border-color 0.15s;
}
.specialist-compact:hover {
  border-color: var(--brand);
}
.specialist-compact__main {
  display: grid;
  gap: 2px;
  min-width: 0;
}
.specialist-compact__main strong {
  color: var(--text-primary);
  font-size: 14px;
}
.specialist-compact__summary {
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.5;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.specialist-compact__meta {
  display: flex;
  gap: 6px;
  align-items: center;
  flex-shrink: 0;
}
.priority-tag {
  display: inline-flex;
  align-items: center;
  height: 22px;
  padding: 0 8px;
  border-radius: var(--card-radius);
  font-size: 11px;
  font-weight: 600;
}
.priority-tag.priority-critical {
  background: rgba(239, 68, 68, 0.12);
  color: #ef4444;
}
.priority-tag.priority-high {
  background: rgba(245, 158, 11, 0.12);
  color: #f59e0b;
}
.priority-tag.priority-medium {
  background: rgba(59, 130, 246, 0.1);
  color: #3b82f6;
}
.priority-tag.priority-low {
  background: rgba(16, 185, 129, 0.1);
  color: #10b981;
}
.conflict-tag {
  display: inline-flex;
  align-items: center;
  height: 22px;
  padding: 0 8px;
  border-radius: var(--card-radius);
  background: rgba(245, 158, 11, 0.12);
  color: #f59e0b;
  font-size: 11px;
  font-weight: 600;
}
.no-data-tag {
  color: var(--text-secondary);
  font-size: 11px;
}

/* AI 建议动作 */
.ai-actions-strip {
  margin-top: 14px;
  padding: 12px 14px;
  border: 1px solid var(--border-color);
  border-radius: var(--card-radius);
  background: var(--bg-surface);
}
.ai-actions-label {
  display: block;
  color: var(--brand);
  font-size: 12px;
  font-weight: 700;
  margin-bottom: 8px;
}
.ai-actions-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.ai-action-chip {
  display: inline-flex;
  align-items: center;
  height: 26px;
  padding: 0 10px;
  border-radius: var(--card-radius);
  background: var(--bg-surface-2);
  color: var(--text-primary);
  font-size: 12px;
}
.ai-action-chip.is-more {
  color: var(--text-secondary);
}

/* 抽屉 */
.drawer-body {
  display: grid;
  gap: 16px;
}
.drawer-section {
  display: grid;
  gap: 8px;
}
.drawer-section-label {
  color: var(--brand);
  font-size: 12px;
  font-weight: 700;
}
.drawer-section p {
  margin: 0;
  color: var(--text-primary);
  font-size: 13px;
  line-height: 1.7;
}
.drawer-section ul {
  margin: 0;
  padding-left: 18px;
  color: var(--text-primary);
  font-size: 13px;
  line-height: 1.7;
}
.drawer-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.drawer-chips span {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border-radius: var(--card-radius);
  background: var(--bg-surface-2);
  color: var(--text-secondary);
  font-size: 12px;
}

@media (max-width: 1100px) {
  .review-summary-row {
    grid-template-columns: 1fr;
  }
  .specialist-compact-list {
    grid-template-columns: 1fr;
  }
}
</style>
