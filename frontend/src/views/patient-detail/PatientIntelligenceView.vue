<template>
  <div class="patient-intelligence">
    <a-card title="AI 分析" :bordered="false">
      <a-tabs>
        <a-tab-pane key="digital-twin" tab="数字孪生">
          <p class="placeholder-text">数字孪生与 What-if 模拟分析</p>
        </a-tab-pane>
        <a-tab-pane key="similar-cases" tab="相似病例">
          <p class="placeholder-text">相似病例检索与结局回溯</p>
        </a-tab-pane>
        <a-tab-pane key="risk-forecast" tab="风险预测">
          <p class="placeholder-text">多维风险预测与趋势分析</p>
        </a-tab-pane>
        <a-tab-pane key="causal" tab="因果分析">
          <p class="placeholder-text">因果推理与干预建议</p>
        </a-tab-pane>
      </a-tabs>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { Card as ACard, Tabs as ATabs, TabPane as ATabPane } from 'ant-design-vue'
</script>

<style scoped>
.patient-intelligence { padding: 16px; }
.placeholder-text { color: #8a94a6; text-align: center; padding: 40px 0; }
</style>
