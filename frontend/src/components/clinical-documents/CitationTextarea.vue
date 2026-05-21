<template>
  <div class="citation-textarea">
    <div
      class="ct-display"
      v-html="renderedHtml"
      @mouseover="onHover"
      @mouseleave="hoveredRef = ''"
    />
    <a-textarea
      v-model:value="text"
      :rows="rows"
      :disabled="disabled"
      class="ct-input"
      @update:value="(value: string) => emit('update:modelValue', value)"
      @blur="emit('update:modelValue', text)"
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

const props = withDefaults(defineProps<{
  modelValue: string
  citations: Citation[]
  rows?: number
  disabled?: boolean
}>(), { rows: 2, disabled: false })

const emit = defineEmits(['update:modelValue'])

const text = ref(props.modelValue)
const hoveredRef = ref('')

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
  return found?.source || hoveredRef.value
})

function onHover(e: MouseEvent) {
  const t = e.target as HTMLElement
  if (t.classList.contains('cite')) {
    hoveredRef.value = t.dataset.ref || ''
  }
}
</script>

<style scoped>
.citation-textarea {
  position: relative;
}
.ct-display {
  padding: 6px 10px;
  border: 1px solid #d9d9d9;
  border-radius: 6px;
  background: #fafafa;
  font-size: 13px;
  line-height: 1.65;
  min-height: 40px;
  margin-bottom: 4px;
  word-break: break-all;
}
.ct-input {
  font-size: 13px;
}
:deep(.cite) {
  display: inline-block;
  padding: 0 4px;
  margin: 0 2px;
  background: #e6f4ff;
  color: #1677ff;
  border-radius: 3px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
}
:deep(.cite:hover) {
  background: #1677ff;
  color: #fff;
}
.ct-tooltip {
  max-width: 260px;
}
.ct-tooltip-ref {
  font-weight: 600;
  color: #1677ff;
  margin-bottom: 2px;
}
.ct-tooltip-source {
  font-size: 12px;
  color: #595959;
}

/* ================= Dark Theme Overrides ================= */
:global(.theme-dark) .ct-display {
  border-color: rgba(125, 167, 214, 0.14);
  background: #091827;
  color: #d9e6f3;
}
:global(.theme-dark) :deep(.cite) {
  background: rgba(34, 211, 238, 0.15);
  color: #22d3ee;
}
:global(.theme-dark) :deep(.cite:hover) {
  background: #22d3ee;
  color: #07111d;
}
:global(.theme-dark) .ct-tooltip-ref {
  color: #22d3ee;
}
:global(.theme-dark) .ct-tooltip-source {
  color: #7f93ab;
}
</style>
