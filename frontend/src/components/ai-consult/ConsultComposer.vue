<template>
  <div class="consult-composer">
    <div class="consult-composer__input-wrap">
      <textarea
        ref="textareaRef"
        :value="modelValue"
        class="consult-composer__textarea"
        :placeholder="placeholder"
        rows="2"
        :disabled="disabled"
        @input="$emit('update:modelValue', ($event.target as HTMLTextAreaElement).value)"
        @keydown.enter.exact.prevent="$emit('send')"
      />
      <button
        class="consult-composer__send"
        type="button"
        :disabled="disabled || !modelValue.trim()"
        @click="$emit('send')"
      >
        发送
      </button>
    </div>
    <div v-if="hint" class="consult-composer__hint">{{ hint }}</div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

defineProps<{
  modelValue: string
  disabled?: boolean
  placeholder?: string
  hint?: string
}>()

defineEmits<{
  'update:modelValue': [value: string]
  send: []
}>()

const textareaRef = ref<HTMLTextAreaElement | null>(null)

function focus() {
  textareaRef.value?.focus()
}

defineExpose({ focus })
</script>

<style scoped>
.consult-composer {
  padding: 12px 16px;
  border-top: 1px solid var(--color-border);
  background: var(--color-bg-surface);
}

.consult-composer__input-wrap {
  display: flex;
  gap: 8px;
  align-items: flex-end;
}

.consult-composer__textarea {
  flex: 1;
  min-height: 40px;
  max-height: 120px;
  padding: 8px 12px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md, 6px);
  background: var(--color-bg-surface);
  color: var(--color-text-primary);
  font-size: 14px;
  font-family: inherit;
  line-height: 1.5;
  resize: vertical;
  transition: border-color 0.15s;
}

.consult-composer__textarea:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: var(--color-primary-bg) 0 0 0 2px;
}

.consult-composer__textarea:disabled {
  background: var(--color-bg-surface-secondary);
  color: var(--color-text-secondary);
  cursor: not-allowed;
}

.consult-composer__send {
  height: 40px;
  padding: 0 16px;
  background: var(--color-primary);
  color: var(--color-text-inverse);
  border: none;
  border-radius: var(--radius-md, 6px);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.15s;
}

.consult-composer__send:hover:not(:disabled) {
  background: var(--color-primary-hover, var(--color-primary));
}

.consult-composer__send:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.consult-composer__hint {
  margin-top: 6px;
  font-size: 12px;
  color: var(--color-text-secondary);
}

@media (max-width: 390px) {
  .consult-composer {
    padding: 8px 12px;
  }

  .consult-composer__textarea {
    font-size: 16px; /* Prevent iOS zoom */
  }
}
</style>
