<template>
  <div class="handover-settings">
    <header class="page-header">
      <h1 class="page-title">班次与数据诊断</h1>
    </header>
    <a-card :bordered="false">
      <p class="placeholder-text">班次配置、数据源诊断、字段映射维护</p>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { Card as ACard } from 'ant-design-vue'
</script>

<style scoped>
.handover-settings { padding: 24px; }
.page-title { font-size: 20px; font-weight: 600; color: #17233D; margin: 0 0 16px; }
.placeholder-text { color: #8a94a6; text-align: center; padding: 40px 0; }
</style>
