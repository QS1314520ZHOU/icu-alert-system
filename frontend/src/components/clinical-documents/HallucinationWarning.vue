<template>
  <AAlert
    type="warning"
    show-icon
    class="hallucination-warning"
  >
    <template #message>
      <span class="hw-title">检测到 {{ warnings.length }} 处需要核对的引用，请重点复核</span>
    </template>
    <template #description>
      <ul class="hw-list">
        <li v-for="(w, i) in warnings" :key="i" class="hw-item">{{ formatClinicalText(w, '请复核引用依据') }}</li>
      </ul>
    </template>
  </AAlert>
</template>

<script setup lang="ts">
import { Alert as AAlert } from 'ant-design-vue'
import { formatClinicalText } from '../../utils/displayLabels'

defineProps<{ warnings: string[] }>()
</script>

<style scoped>
.hallucination-warning {
  margin: 8px 0 12px;
  border-radius: var(--card-radius);
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
:global(html[data-theme='dark']) .hw-item {
  color: var(--warning);
}
</style>

