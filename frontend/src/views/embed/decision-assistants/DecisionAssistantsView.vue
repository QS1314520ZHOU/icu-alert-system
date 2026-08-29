<template>
  <div class="decision-assistants">
    <div class="da-not-connected">
      <div class="da-icon">🔧</div>
      <h3 class="da-title">决策助手</h3>
      <p class="da-message">数据源未连接</p>
      <p class="da-detail">该模块的后端API尚未实现。当前无法提供真实的临床决策辅助数据。</p>
      <div class="da-features">
        <p class="da-features-title">预期功能：</p>
        <ul class="da-features-list">
          <li>镇静镇痛策略建议</li>
          <li>脱机拔管评估</li>
          <li>营养支持方案</li>
          <li>抗感染策略</li>
          <li>液体管理建议</li>
          <li>VTE预防方案</li>
          <li>血糖控制建议</li>
          <li>压疮预防措施</li>
        </ul>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useEmbedBridge } from '../../../composables/useEmbedBridge'

const { sendUpdateTitle } = useEmbedBridge({
  moduleKey: 'decision-assistants',
  targetOrigin: window.location.origin,
})

onMounted(() => {
  sendUpdateTitle('决策助手')
})
</script>

<style scoped>
.decision-assistants {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 400px;
}

.da-not-connected {
  text-align: center;
  padding: 48px 32px;
  max-width: 480px;
}

.da-icon {
  font-size: 48px;
  margin-bottom: 16px;
}

.da-title {
  margin: 0 0 8px;
  font-size: 20px;
  font-weight: 600;
  color: #182230;
}

.da-message {
  margin: 0 0 8px;
  font-size: 16px;
  font-weight: 500;
  color: #F59E0B;
}

.da-detail {
  margin: 0 0 24px;
  font-size: 14px;
  color: #52606D;
  line-height: 1.5;
}

.da-features {
  text-align: left;
  background: #F8FAFC;
  border-radius: 8px;
  padding: 16px 20px;
  border: 1px solid #E8EEF5;
}

.da-features-title {
  margin: 0 0 8px;
  font-size: 13px;
  font-weight: 600;
  color: #52606D;
}

.da-features-list {
  margin: 0;
  padding-left: 20px;
  font-size: 13px;
  color: #52606D;
  line-height: 1.8;
}
</style>

