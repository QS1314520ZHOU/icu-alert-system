<template>
  <a-card :bordered="false" class="mdt-step-card">
    <div class="step-card__head">
      <div>
        <span class="step-kicker">第二步</span>
        <h2>冲突评审与专科意见</h2>
        <p>先看总控结论和冲突焦点，再决定是否同步为决议草案。</p>
      </div>
      <a-button type="primary" :disabled="isGeneratingAssessment" @click="$emit('next')">进入决议确认</a-button>
    </div>

    <section class="review-grid">
      <article class="review-card review-card--summary">
        <span>总控结论</span>
        <strong>{{ mdtSeverityLabel }}</strong>
        <p>{{ metaSummary }}</p>
      </article>

      <article class="review-card">
        <div class="review-card__head">
          <span>冲突焦点</span>
          <b>{{ conflictRows.length }} 项</b>
        </div>
        <div v-if="conflictRows.length" class="compact-list">
          <div v-for="(item, index) in conflictRows.slice(0, 4)" :key="item.id || index">
            <strong>{{ item.summary || '跨专科意见不一致' }}</strong>
            <small>{{ formatAgents(item.agents) }}</small>
          </div>
        </div>
        <div v-else class="empty-box">当前尚未识别到明显跨专科冲突。</div>
      </article>
    </section>

    <section class="system-card-grid">
      <button
        v-for="item in systemCards"
        :key="item.agent"
        type="button"
        :class="['system-card', `is-${item.priority || 'medium'}`, { 'is-active': activeSpecialist?.agent === item.agent }]"
        @click="$emit('select-specialist', item.agent)"
      >
        <span>{{ item.label }}</span>
        <strong>{{ priorityLabel(item.priority) }}</strong>
        <small>{{ item.summary }}</small>
      </button>
    </section>

    <section class="review-grid">
      <article class="review-card">
        <div class="review-card__head">
          <span>当前专科意见</span>
          <b>{{ activeSystemLabel }}</b>
        </div>
        <p>{{ activeSpecialist?.summary || (isGeneratingAssessment ? '正在生成专科意见。' : '点击上方系统卡片查看专科摘要。') }}</p>
      </article>

      <article class="review-card">
        <div class="review-card__head">
          <span>AI 建议动作草案</span>
          <b>{{ syncableAiActions.length }} 条</b>
        </div>
        <div v-if="syncableAiActions.length" class="compact-list">
          <div v-for="item in syncableAiActions.slice(0, 5)" :key="item">
            <strong>{{ item }}</strong>
          </div>
        </div>
        <div v-else class="empty-box">当前尚未形成动作草案，可在下一步手动新增。</div>
      </article>
    </section>

    <a-collapse class="detail-collapse">
      <a-collapse-panel key="detail" header="查看专科深度分析">
        <div v-if="activeSpecialist" class="detail-stack">
          <section>
            <span>关注点</span>
            <ul>
              <li v-for="(item, index) in activeSpecialist.concerns || []" :key="`concern-${index}`">{{ item }}</li>
            </ul>
          </section>
          <section>
            <span>建议</span>
            <ul>
              <li v-for="(item, index) in activeSpecialist.recommendations || []" :key="`rec-${index}`">{{ item }}</li>
            </ul>
          </section>
          <section>
            <span>证据线索</span>
            <div class="chip-row">
              <em v-for="(item, index) in activeSpecialist.evidence || []" :key="`evidence-${index}`">{{ item }}</em>
            </div>
          </section>
        </div>
        <div v-else class="empty-box">暂无可展开的专科深度分析。</div>
      </a-collapse-panel>
    </a-collapse>

    <div class="step-actions">
      <a-button :disabled="!syncableAiActions.length || isGeneratingAssessment" @click="$emit('sync-decisions')">同步 AI 动作为决议</a-button>
      <span v-if="!syncableAiActions.length">当前尚未形成决议，可在下一步手动新增。</span>
      <a-button type="primary" @click="$emit('next')">进入决议确认</a-button>
    </div>
  </a-card>
</template>

<script setup lang="ts">
import { Button as AButton, Card as ACard, Collapse as ACollapse, CollapsePanel as ACollapsePanel } from 'ant-design-vue'

defineProps<{
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
void ACollapse
void ACollapsePanel

function priorityLabel(priority: any) {
  const key = String(priority || 'medium').toLowerCase()
  return ({ critical: '危急', high: '高优先', medium: '中优先', low: '低优先' } as Record<string, string>)[key] || '中优先'
}

function domainLabel(domain: any) {
  const key = String(domain || '')
  return ({
    hemodynamic: '循环',
    respiratory: '呼吸',
    infection: '感染',
    renal: '肾脏',
    neuro: '神经',
    nutrition: '营养',
    pharmacy: '药学',
    hemodynamic_agent: '循环',
    respiratory_agent: '呼吸',
    infection_agent: '感染',
    renal_agent: '肾脏',
    neuro_agent: '神经',
    nutrition_agent: '营养',
    pharmacy_agent: '药学',
  } as Record<string, string>)[key] || key || '多专科'
}

function formatAgents(agents: any) {
  return Array.isArray(agents) && agents.length ? agents.map(domainLabel).join(' / ') : '多专科'
}
</script>

<style scoped>
.mdt-step-card,
.review-card {
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 12px;
  background: rgba(15, 23, 42, 0.66);
}
.step-card__head,
.review-card__head,
.step-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
}
.step-kicker,
.review-card span,
.detail-stack span {
  color: rgba(125, 211, 252, 0.86);
  font-size: 12px;
  font-weight: 700;
}
h2 {
  margin: 4px 0 6px;
  color: #f8fafc;
}
p {
  margin: 0;
  color: rgba(203, 213, 225, 0.74);
  line-height: 1.6;
}
.review-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
  margin-top: 16px;
}
.review-card {
  padding: 16px;
}
.review-card strong,
.review-card b {
  display: block;
  margin: 6px 0;
  color: #f8fafc;
  font-size: 18px;
}
.compact-list {
  display: grid;
  gap: 10px;
}
.compact-list div {
  padding: 10px;
  border-radius: 8px;
  background: rgba(2, 6, 23, 0.3);
}
.compact-list strong {
  margin: 0;
  font-size: 14px;
}
.compact-list small,
.empty-box,
.step-actions span {
  color: rgba(148, 163, 184, 0.82);
}
.system-card-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-top: 16px;
}
.system-card {
  min-height: 118px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 10px;
  padding: 12px;
  color: #e2e8f0;
  text-align: left;
  cursor: pointer;
  background: rgba(2, 6, 23, 0.3);
}
.system-card.is-active {
  border-color: rgba(56, 189, 248, 0.62);
  background: rgba(14, 116, 144, 0.24);
}
.system-card.is-critical,
.system-card.is-high {
  border-color: rgba(248, 113, 113, 0.4);
}
.system-card span,
.system-card strong,
.system-card small {
  display: block;
}
.system-card strong {
  margin: 6px 0;
  color: #f8fafc;
}
.system-card small {
  color: rgba(203, 213, 225, 0.68);
  line-height: 1.4;
}
.detail-collapse {
  margin-top: 16px;
  border-radius: 10px;
  overflow: hidden;
  background: rgba(2, 6, 23, 0.28);
}
.detail-stack {
  display: grid;
  gap: 14px;
  color: rgba(226, 232, 240, 0.82);
}
.chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.chip-row em {
  padding: 6px 10px;
  border-radius: 999px;
  color: #cbd5e1;
  font-style: normal;
  background: rgba(30, 41, 59, 0.82);
}
.step-actions {
  margin-top: 16px;
}
@media (max-width: 1100px) {
  .system-card-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .review-grid {
    grid-template-columns: 1fr;
  }
}

:global(html[data-theme='light']) .mdt-step-card,
:global(html[data-theme='light']) .review-card,
:global(html[data-theme='light']) .system-card {
  border-color: #dbeafe;
  background: #ffffff;
  box-shadow: 0 12px 30px rgba(15, 23, 42, 0.06);
}
:global(html[data-theme='light']) .step-kicker,
:global(html[data-theme='light']) .review-card span,
:global(html[data-theme='light']) .detail-stack span {
  color: #0284c7;
}
:global(html[data-theme='light']) h2,
:global(html[data-theme='light']) .review-card strong,
:global(html[data-theme='light']) .review-card b,
:global(html[data-theme='light']) .system-card strong {
  color: #0f172a;
}
:global(html[data-theme='light']) p,
:global(html[data-theme='light']) .system-card,
:global(html[data-theme='light']) .detail-stack {
  color: #475569;
}
:global(html[data-theme='light']) .compact-list div,
:global(html[data-theme='light']) .chip-row em {
  background: #f1f5f9;
}
:global(html[data-theme='light']) .compact-list small,
:global(html[data-theme='light']) .empty-box,
:global(html[data-theme='light']) .step-actions span,
:global(html[data-theme='light']) .system-card small {
  color: #64748b;
}
:global(html[data-theme='light']) .system-card.is-active {
  border-color: #38bdf8;
  background: #e0f2fe;
}
:global(html[data-theme='light']) .detail-collapse {
  background: #ffffff;
}
</style>
