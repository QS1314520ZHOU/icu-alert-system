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
  border: 1px solid rgba(125,167,214,.15);
  border-radius: 8px;
  background: rgba(255,255,255,.04);
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
  color: #dce6f0;
  transition: background .15s;
}
.collapse-panel__header:hover {
  background: rgba(255,255,255,.04);
}
.collapse-panel__chevron {
  font-size: 10px;
  color: #8fa3b8;
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
  background: rgba(45,140,255,.18);
  color: #6da5ff;
}
.collapse-panel__digest {
  flex: 1;
  font-weight: 400;
  font-size: 12px;
  color: #7f93ab;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.collapse-panel__body {
  padding: 0 12px 12px;
  border-top: 1px solid rgba(125,167,214,.08);
}
.collapse-panel--danger .collapse-panel__badge { background: rgba(217,52,43,.2); color: #ff6b6b; }
.collapse-panel--warn .collapse-panel__badge { background: rgba(255,170,0,.2); color: #ffb347; }
.collapse-panel--info .collapse-panel__badge { background: rgba(45,140,255,.18); color: #6da5ff; }

/* Light theme overrides */
html[data-theme='light'] .collapse-panel {
  background: rgba(243,248,252,0.96);
  border-color: rgba(187,204,220,0.72);
}
html[data-theme='light'] .collapse-panel__header {
  color: #1a2332;
}
html[data-theme='light'] .collapse-panel__header:hover {
  background: rgba(226,240,234,0.5);
}
html[data-theme='light'] .collapse-panel__chevron {
  color: #6b7f96;
}
html[data-theme='light'] .collapse-panel__badge {
  background: rgba(45,140,255,.12);
  color: #1d6f63;
}
html[data-theme='light'] .collapse-panel__digest {
  color: #66766b;
}
html[data-theme='light'] .collapse-panel__body {
  border-top-color: rgba(187,204,220,0.4);
}
html[data-theme='light'] .collapse-panel--danger .collapse-panel__badge { background: rgba(248,113,113,.15); color: #dc2626; }
html[data-theme='light'] .collapse-panel--warn .collapse-panel__badge { background: rgba(245,158,11,.15); color: #d97706; }
html[data-theme='light'] .collapse-panel--info .collapse-panel__badge { background: rgba(45,140,255,.12); color: #2563eb; }
</style>