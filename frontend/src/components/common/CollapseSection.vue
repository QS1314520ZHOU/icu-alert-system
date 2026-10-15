<template>
  <div class="collapse-section" :class="{ 'is-open': isOpen }">
    <div class="collapse-header" @click="toggle">
      <div class="collapse-header-left">
        <span class="collapse-arrow">{{ isOpen ? '▾' : '▸' }}</span>
        <slot name="title" />
      </div>
      <div class="collapse-header-right">
        <slot name="extra" />
      </div>
    </div>
    <transition name="collapse-slide">
      <div v-show="isOpen" class="collapse-body">
        <slot />
      </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'

const props = withDefaults(defineProps<{
  defaultOpen?: boolean
  preload?: boolean
}>(), {
  defaultOpen: false,
  preload: false,
})

const isOpen = ref(props.defaultOpen)

function toggle() {
  isOpen.value = !isOpen.value
}

onMounted(() => {
  if (props.preload) {
    isOpen.value = true
    setTimeout(() => { isOpen.value = props.defaultOpen }, 800)
  }
})
</script>

<style scoped>
.collapse-section {
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  overflow: hidden;
  transition: border-color 0.2s;
}
.collapse-section:hover {
  border-color: var(--color-border);
}
.collapse-section.is-open {
  border-color: var(--color-primary);
}

.collapse-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 20px;
  cursor: pointer;
  user-select: none;
  transition: background 0.15s;
}
.collapse-header:hover {
  background: var(--color-bg-inset);
}

.collapse-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.collapse-arrow {
  font-size: 12px;
  color: var(--color-text-tertiary);
  transition: transform 0.2s;
  flex-shrink: 0;
  width: 14px;
  text-align: center;
}

.collapse-header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.collapse-body {
  padding: 0 20px 16px;
}

.collapse-slide-enter-active,
.collapse-slide-leave-active {
  transition: all 0.2s ease;
  overflow: hidden;
}
.collapse-slide-enter-from,
.collapse-slide-leave-to {
  opacity: 0;
  max-height: 0;
  padding-top: 0;
  padding-bottom: 0;
}
.collapse-slide-enter-to,
.collapse-slide-leave-from {
  opacity: 1;
  max-height: 2000px;
}
</style>
