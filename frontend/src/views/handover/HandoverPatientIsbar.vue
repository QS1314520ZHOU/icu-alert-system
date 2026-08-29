<template>
  <div class="handover-patient-isbar">
    <header class="page-header">
      <h1 class="page-title">患者ISBAR交班</h1>
    </header>
    <a-card :bordered="false">
      <p class="placeholder-text">单患者ISBAR结构化编辑器 — 三栏布局（患者列表 / ISBAR编辑 / 数据证据）</p>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { Card as ACard } from 'ant-design-vue'
</script>

<style scoped>
.handover-patient-isbar { padding: 24px; }
.page-title { font-size: 20px; font-weight: 600; color: #17233D; margin: 0 0 16px; }
.placeholder-text { color: #8a94a6; text-align: center; padding: 40px 0; }
</style>
