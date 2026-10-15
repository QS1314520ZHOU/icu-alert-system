<template>
  <div class="collapse-panel" :class="[`collapse-panel--${tone}`]">
    <div class="collapse-panel__header" @click="toggle">
      <span class="collapse-panel__chevron">{{ open ? '▾' : '▸' }}</span>
      <span class="collapse-panel__title">{{ title }}</span>
      <span v-if="badge" class="collapse-panel__badge">{{ badge }}</span>
      <span v-if="digest" class="collapse-panel__digest">{{ digest }}</span>
    </div>
    <div v-show="open" class="collapse-panel__body">
      <slot />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'

const props = withDefaults(defineProps<{
  title: string
  badge?: string | number
  tone?: 'neutral' | 'info' | 'warn' | 'danger'
  digest?: string
  storageKey?: string
  defaultOpen?: boolean
  forceOpen?: boolean
}>(), {
  tone: 'neutral',
  defaultOpen: false,
  forceOpen: false,
})

const open = ref(props.defaultOpen)

if (props.storageKey) {
  const stored = localStorage.getItem(`collapse-${props.storageKey}`)
  if (stored !== null) {
    open.value = stored === 'true'
  }
}

watch(open, (val) => {
  if (props.storageKey) {
    localStorage.setItem(`collapse-${props.storageKey}`, String(val))
  }
})

watch(() => props.forceOpen, (val) => {
  if (val) open.value = true
}, { immediate: true })

function toggle() {
  open.value = !open.value
}
</script>

<style scoped>
.collapse-panel {
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--bg-surface);
  margin-bottom: 8px;
  overflow: hidden;
}
.collapse-panel__header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  cursor: pointer;
  user-select: none;
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-inverse);
  transition: background .15s;
}
.collapse-panel__header:hover {
  background: var(--color-bg-surface-secondary);
}
.collapse-panel__chevron {
  font-size: 10px;
  color: var(--color-text-tertiary);
  flex: 0 0 12px;
}
.collapse-panel__title {
  flex: 0 0 auto;
}
.collapse-panel__badge {
  padding: 1px 8px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 700;
  background: var(--color-primary-bg);
  color: var(--color-primary);
}
.collapse-panel__digest {
  flex: 1;
  font-weight: 400;
  font-size: 12px;
  color: var(--color-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.collapse-panel__body {
  padding: 0 12px 12px;
  border-top: 1px solid var(--color-divider);
}
.collapse-panel--danger .collapse-panel__badge { background: var(--color-danger-bg); color: var(--color-danger); }
.collapse-panel--warn .collapse-panel__badge { background: var(--color-warning-bg); color: var(--color-warning); }
.collapse-panel--info .collapse-panel__badge { background: var(--color-primary-bg); color: var(--color-primary); }

/* Light theme overrides */
html[data-theme='light'] .collapse-panel {
  background: var(--color-bg-surface-secondary);
  border-color: var(--color-border);
}
html[data-theme='light'] .collapse-panel__header {
  color: var(--color-text-primary);
}
html[data-theme='light'] .collapse-panel__header:hover {
  background: var(--color-bg-inset);
}
html[data-theme='light'] .collapse-panel__chevron {
  color: var(--color-text-secondary);
}
html[data-theme='light'] .collapse-panel__badge {
  background: var(--color-primary-bg);
  color: var(--color-primary);
}
html[data-theme='light'] .collapse-panel__digest {
  color: var(--color-text-secondary);
}
html[data-theme='light'] .collapse-panel__body {
  border-top-color: var(--color-divider);
}
html[data-theme='light'] .collapse-panel--danger .collapse-panel__badge { background: var(--color-danger-bg); color: var(--color-danger); }
html[data-theme='light'] .collapse-panel--warn .collapse-panel__badge { background: var(--color-warning-bg); color: var(--color-warning); }
html[data-theme='light'] .collapse-panel--info .collapse-panel__badge { background: var(--color-primary-bg); color: var(--color-primary); }
</style>