<template>
  <div class="citation-textarea">
    <div
      v-if="!editing"
      :class="['ct-display', { 'ct-display--compact': compact }]"
      v-html="renderedHtml"
      @dblclick="startEditing"
      @mouseover="onHover"
      @mouseleave="hoveredRef = ''"
    />
    <a-textarea
      v-else
      :value="text"
      :rows="rows"
      :disabled="disabled"
      class="ct-input"
      @update:value="onInput"
      @blur="finishEditing"
    />
    <a-popover
      v-if="hoveredRef && tooltipSource"
      :open="true"
      placement="top"
    >
      <template #content>
        <div class="ct-tooltip">
          <div class="ct-tooltip-ref">[{{ hoveredRef }}]</div>
          <div class="ct-tooltip-source">{{ tooltipSource }}</div>
        </div>
      </template>
      <span />
    </a-popover>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { Textarea as ATextarea, Popover as APopover } from 'ant-design-vue'
import type { Citation } from '../../api/clinicalDocuments'
import { formatClinicalText, formatClinicalTermLabel } from '../../utils/displayLabels'

const props = withDefaults(defineProps<{
  modelValue: string
  citations: Citation[]
  rows?: number
  disabled?: boolean
  editable?: boolean
  compact?: boolean
}>(), { rows: 2, disabled: false, editable: false, compact: false })

const emit = defineEmits(['update:modelValue'])

const text = ref(props.modelValue)
const hoveredRef = ref('')
const editing = ref(props.editable)

watch(() => props.modelValue, (v) => { text.value = v })

const renderedHtml = computed(() =>
  (text.value || '').replace(
    /\[([A-Z]+\d*)\]/g,
    (_, r: string) => `<span class="cite" data-ref="${r}">[${r}]</span>`,
  ),
)

const tooltipSource = computed(() => {
  if (!hoveredRef.value) return ''
  const found = props.citations.find((c) => c.ref === hoveredRef.value)
  return sourceLabel(found?.source || hoveredRef.value)
})

function onHover(e: MouseEvent) {
  const t = e.target as HTMLElement
  if (t.classList.contains('cite')) {
    hoveredRef.value = t.dataset.ref || ''
  }
}

function onInput(value: string) {
  text.value = value
  emit('update:modelValue', value)
}

function startEditing() {
  if (props.disabled) return
  editing.value = true
}

function finishEditing() {
  emit('update:modelValue', text.value)
  editing.value = false
}

function sourceLabel(source: string): string {
  const value = String(source || '')
  const direct: Record<string, string> = {
    vitals: '生命体征',
    ventilator_current: '呼吸机当前参数',
    vent_change: '呼吸机调整',
    scores: '评分',
  }
  if (direct[value]) return direct[value]
  if (value.startsWith('lab:')) return `化验：${formatClinicalText(value.slice(4), '检验')}`
  if (value.startsWith('drug:')) return `用药：${formatClinicalText(value.slice(5), '用药')}`
  if (value.startsWith('alert:')) return `告警：${alertTypeLabel(value.slice(6))}`
  return formatClinicalTermLabel(value, '引用依据')
}

function alertTypeLabel(type: string) {
  const map: Record<string, string> = {
    aki: '急性肾损伤',
    sepsis: '脓毒症',
    hypotension: '低血压',
    hypoxemia: '低氧',
  }
  return map[String(type || '').toLowerCase()] || formatClinicalTermLabel(type, '风险提醒')
}
</script>

<style scoped>
.citation-textarea {
  position: relative;
}
.ct-display {
  padding: 6px 10px;
  border: 1px solid #d9d9d9;
  border-radius: var(--card-radius);
  background: var(--bg-surface);
  font-size: 13px;
  line-height: 1.65;
  min-height: 40px;
  margin-bottom: 4px;
  word-break: break-word;
  white-space: pre-wrap;
  cursor: text;
}
.ct-display--compact {
  max-height: 92px;
  overflow: auto;
}
.ct-input {
  font-size: 13px;
}
:deep(.cite) {
  display: inline-block;
  padding: 0 4px;
  margin: 0 2px;
  background: var(--bg-surface);
  color: var(--brand);
  border-radius: var(--card-radius);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
}
:deep(.cite:hover) {
  background: var(--brand);
  color: var(--text-primary);
}
.ct-tooltip {
  max-width: 260px;
}
.ct-tooltip-ref {
  font-weight: 600;
  color: var(--brand);
  margin-bottom: 2px;
}
.ct-tooltip-source {
  font-size: 12px;
  color: #595959;
}

/* ================= Dark Theme Overrides ================= */
:global(html[data-theme='dark']) .ct-display {
  border-color: rgba(125, 167, 214, 0.14);
  background: var(--bg-surface);
  color: var(--text-primary);
}
:global(html[data-theme='dark']) :deep(.cite) {
  background: rgba(34, 211, 238, 0.15);
  color: var(--brand);
}
:global(html[data-theme='dark']) :deep(.cite:hover) {
  background: var(--brand);
  color: #07111d;
}
:global(html[data-theme='dark']) .ct-tooltip-ref {
  color: var(--brand);
}
:global(html[data-theme='dark']) .ct-tooltip-source {
  color: #7f93ab;
}
</style>

