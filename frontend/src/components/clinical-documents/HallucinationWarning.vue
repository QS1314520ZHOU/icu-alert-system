<template>
  <a-alert
    type="warning"
    show-icon
    class="hallucination-warning"
  >
    <template #message>
      <span class="hw-title">⚠️ 检测到 {{ warnings.length }} 处可疑引用，请重点核对</span>
    </template>
    <template #description>
      <ul class="hw-list">
        <li v-for="(w, i) in warnings" :key="i" class="hw-item">{{ w }}</li>
      </ul>
    </template>
  </a-alert>
</template>

<script setup lang="ts">
defineProps<{ warnings: string[] }>()
</script>

<style scoped>
.hallucination-warning {
  margin: 8px 0 12px;
  border-radius: 8px;
}
.hw-title {
  font-weight: 600;
  font-size: 14px;
}
.hw-list {
  margin: 4px 0 0;
  padding-left: 18px;
}
.hw-item {
  font-size: 13px;
  line-height: 1.7;
  color: #d48806;
}

/* ================= Dark Theme Overrides ================= */
:global(.theme-dark) .hw-item {
  color: #fbbf24;
}
</style>
