<template>
  <div class="handover-patients">
    <header class="page-header">
      <h1 class="page-title">患者交班</h1>
    </header>
    <a-card :bordered="false">
      <p class="placeholder-text">患者交班列表 — 每个患者的ISBAR交班状态与进度</p>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { Card as ACard } from 'ant-design-vue'
</script>

<style scoped>
.handover-patients { padding: 24px; }
.page-title { font-size: 20px; font-weight: 600; color: #17233D; margin: 0 0 16px; }
.placeholder-text { color: #8a94a6; text-align: center; padding: 40px 0; }
</style>
