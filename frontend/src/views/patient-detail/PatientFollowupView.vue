<template>
  <div class="patient-followup">
    <a-card title="随访管理" :bordered="false">
      <a-tabs>
        <a-tab-pane key="pics" tab="PICS评估">
          <p class="placeholder-text">ICU后综合征（PICS）风险评估与管理</p>
        </a-tab-pane>
        <a-tab-pane key="followup-tasks" tab="随访任务">
          <p class="placeholder-text">出院后随访计划与任务跟踪</p>
        </a-tab-pane>
        <a-tab-pane key="rehab" tab="康复转介">
          <p class="placeholder-text">康复科转介与随访记录</p>
        </a-tab-pane>
      </a-tabs>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { Card as ACard, Tabs as ATabs, TabPane as ATabPane } from 'ant-design-vue'
</script>

<style scoped>
.patient-followup { padding: 16px; }
.placeholder-text { color: #8a94a6; text-align: center; padding: 40px 0; }
</style>
