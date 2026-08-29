<template>
  <div :class="['consult-msg', `consult-msg--${message.role}`]">
    <div :class="['consult-msg__bubble', `consult-msg__bubble--${message.role}`]">
      <!-- Intent tag -->
      <div v-if="message.intentPrimary || message.messageType === 'clarification'" class="consult-msg__intent">
        <span
          v-if="message.intentPrimary"
          :class="['consult-msg__intent-tag', intentTagClass(message.intentFocusSection)]"
        >
          {{ intentTagLabel(message.intentPrimary, message.intentFocusSection) }}
        </span>
        <span v-if="message.messageType === 'clarification'" class="consult-msg__intent-tag is-clarify">
          需补充信息
        </span>
      </div>

      <!-- High risk banner -->
      <div v-if="message.isHighRisk" class="consult-msg__risk-banner">
        高风险建议，请确认后执行
      </div>

      <!-- Structured sections -->
      <template v-if="message.sections?.length">
        <div
          v-for="(section, sIdx) in message.sections"
          :key="`s-${sIdx}`"
          :class="['consult-msg__section', sectionClass(section.title)]"
        >
          <div
            class="consult-msg__section-header"
            @click="$emit('toggle-section', message.id, sIdx)"
          >
            <span class="consult-msg__section-title">{{ section.title }}</span>
            <span
              v-if="section.title === '下一步处理建议'"
              class="consult-msg__section-count"
            >
              {{ section.lines.length }} 项
            </span>
            <svg
              :class="['consult-msg__section-arrow', { 'is-open': !section.collapsed }]"
              width="12" height="12" viewBox="0 0 12 12"
            >
              <path d="M3 4.5L6 7.5L9 4.5" stroke="currentColor" stroke-width="1.5" fill="none"/>
            </svg>
          </div>
          <div v-show="!section.collapsed" class="consult-msg__section-body">
            <div
              v-for="(line, lIdx) in section.lines"
              :key="`l-${lIdx}`"
              class="consult-msg__section-line"
            >
              <span
                v-if="section.title === '下一步处理建议'"
                :class="['consult-msg__priority', priorityClass(lIdx)]"
              >
                {{ priorityLabel(lIdx) }}
              </span>
              {{ line }}
            </div>
          </div>
        </div>
      </template>

      <!-- Plain text -->
      <div v-else-if="message.content" class="consult-msg__text">
        {{ message.content }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  intentPrimary?: string
  intentFocusSection?: string
  messageType?: string
  isHighRisk?: boolean
  sections?: Array<{
    title: string
    lines: string[]
    collapsed?: boolean
  }>
}

defineProps<{
  message: Message
}>()

defineEmits<{
  'toggle-section': [messageId: string, sectionIndex: number]
}>()

function intentTagClass(section?: string): string {
  if (section === 'circulatory') return 'is-circulatory'
  if (section === 'respiratory') return 'is-respiratory'
  if (section === 'infection') return 'is-infection'
  if (section === 'renal') return 'is-renal'
  if (section === 'neurologic') return 'is-neurologic'
  return 'is-general'
}

function intentTagLabel(primary?: string, _section?: string): string {
  const labels: Record<string, string> = {
    risk_analysis: '风险分析',
    treatment_plan: '处理计划',
    differential: '鉴别诊断',
    monitoring: '监护建议',
    summary: '摘要',
  }
  return labels[primary || ''] || '分析'
}

function sectionClass(title: string): string {
  if (title.includes('风险')) return 'is-risk'
  if (title.includes('建议') || title.includes('处理')) return 'is-action'
  if (title.includes('证据') || title.includes('依据')) return 'is-evidence'
  return 'is-default'
}

function priorityClass(index: number): string {
  if (index === 0) return 'is-p1'
  if (index === 1) return 'is-p2'
  return 'is-p3'
}

function priorityLabel(index: number): string {
  if (index === 0) return 'P1'
  if (index === 1) return 'P2'
  return 'P3'
}
</script>

<style scoped>
.consult-msg {
  display: flex;
  margin-bottom: 12px;
}

.consult-msg--user {
  justify-content: flex-end;
}

.consult-msg--assistant {
  justify-content: flex-start;
}

.consult-msg__bubble {
  max-width: 80%;
  padding: 10px 14px;
  border-radius: var(--radius-lg, 8px);
  font-size: 14px;
  line-height: 1.6;
}

.consult-msg__bubble--user {
  background: var(--color-primary, #2563EB);
  color: #FFFFFF;
  border-bottom-right-radius: 4px;
}

.consult-msg__bubble--assistant {
  background: var(--color-bg-surface, #FFFFFF);
  color: var(--color-text-primary, #18212B);
  border: 1px solid var(--color-border, #E3E7EC);
  border-bottom-left-radius: 4px;
}

/* Intent tags */
.consult-msg__intent {
  display: flex;
  gap: 6px;
  margin-bottom: 8px;
}

.consult-msg__intent-tag {
  display: inline-flex;
  padding: 2px 8px;
  border-radius: var(--radius-tag, 4px);
  font-size: 11px;
  font-weight: 600;
  background: var(--color-primary-bg, rgba(37, 99, 235, 0.08));
  color: var(--color-primary, #2563EB);
}

.consult-msg__intent-tag.is-circulatory {
  background: var(--color-danger-bg, rgba(217, 45, 32, 0.08));
  color: var(--color-danger, #D92D20);
}

.consult-msg__intent-tag.is-respiratory {
  background: var(--color-warning-bg, rgba(181, 71, 8, 0.08));
  color: var(--color-warning, #B54708);
}

.consult-msg__intent-tag.is-infection {
  background: rgba(168, 85, 247, 0.08);
  color: #7C3AED;
}

.consult-msg__intent-tag.is-clarify {
  background: var(--color-warning-bg, rgba(181, 71, 8, 0.08));
  color: var(--color-warning, #B54708);
}

/* Risk banner */
.consult-msg__risk-banner {
  padding: 6px 10px;
  margin-bottom: 8px;
  background: var(--color-danger-bg, rgba(217, 45, 32, 0.08));
  color: var(--color-danger, #D92D20);
  border-radius: var(--radius-md, 6px);
  font-size: 12px;
  font-weight: 600;
}

/* Sections */
.consult-msg__section {
  margin-bottom: 8px;
  border: 1px solid var(--color-border, #E3E7EC);
  border-radius: var(--radius-md, 6px);
  overflow: hidden;
}

.consult-msg__section-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 10px;
  background: var(--color-bg-surface-secondary, #F1F3F5);
  cursor: pointer;
  user-select: none;
}

.consult-msg__section-title {
  flex: 1;
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-primary, #18212B);
}

.consult-msg__section-count {
  font-size: 11px;
  color: var(--color-text-secondary, #667085);
}

.consult-msg__section-arrow {
  transition: transform 0.15s;
  color: var(--color-text-secondary, #667085);
}

.consult-msg__section-arrow.is-open {
  transform: rotate(180deg);
}

.consult-msg__section-body {
  padding: 8px 10px;
}

.consult-msg__section-line {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  padding: 4px 0;
  font-size: 13px;
  line-height: 1.5;
  color: var(--color-text-primary, #18212B);
}

/* Priority dots */
.consult-msg__priority {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  font-size: 10px;
  font-weight: 700;
}

.consult-msg__priority.is-p1 {
  background: var(--color-danger-bg, rgba(217, 45, 32, 0.08));
  color: var(--color-danger, #D92D20);
}

.consult-msg__priority.is-p2 {
  background: var(--color-warning-bg, rgba(181, 71, 8, 0.08));
  color: var(--color-warning, #B54708);
}

.consult-msg__priority.is-p3 {
  background: var(--color-primary-bg, rgba(37, 99, 235, 0.08));
  color: var(--color-primary, #2563EB);
}

/* Text */
.consult-msg__text {
  white-space: pre-wrap;
  word-break: break-word;
}

@media (max-width: 390px) {
  .consult-msg__bubble {
    max-width: 90%;
  }
}
</style>
