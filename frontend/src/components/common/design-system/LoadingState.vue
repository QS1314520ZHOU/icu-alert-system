<template>
  <div class="loading-state">
    <div class="loading-state__spinner">
      <div class="loading-state__dot" />
      <div class="loading-state__dot" />
      <div class="loading-state__dot" />
    </div>
    <p v-if="message" class="loading-state__message">{{ message }}</p>
  </div>
</template>

<script setup lang="ts">
interface Props {
  message?: string
}

defineProps<Props>()
</script>

<style scoped>
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 24px;
  text-align: center;
}

.loading-state__spinner {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
}

.loading-state__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--color-primary, #2563EB);
  animation: loading-bounce 1.4s ease-in-out infinite both;
}

.loading-state__dot:nth-child(1) {
  animation-delay: -0.32s;
}

.loading-state__dot:nth-child(2) {
  animation-delay: -0.16s;
}

@keyframes loading-bounce {
  0%, 80%, 100% {
    transform: scale(0);
    opacity: 0.5;
  }
  40% {
    transform: scale(1);
    opacity: 1;
  }
}

.loading-state__message {
  font-size: var(--text-body, 14px);
  color: var(--color-text-secondary, #667085);
  margin: 0;
}
</style>
