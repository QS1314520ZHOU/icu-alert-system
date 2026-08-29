<template>
  <div class="handover-tasks">
    <header class="page-header">
      <h1 class="page-title">待办与未闭环</h1>
    </header>
    <a-card :bordered="false">
      <p class="placeholder-text">未闭环危急值、待执行医嘱、逾期任务清单</p>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { Card as ACard } from 'ant-design-vue'
</script>

<style scoped>
.handover-tasks { padding: 24px; }
.page-title { font-size: 20px; font-weight: 600; color: #17233D; margin: 0 0 16px; }
.placeholder-text { color: #8a94a6; text-align: center; padding: 40px 0; }
</style>
