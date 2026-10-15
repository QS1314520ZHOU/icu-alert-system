<template>
  <div class="offline-pipeline">
    <div class="pipeline-header">
      <h3 class="pipeline-title">离线包构建管道</h3>
      <div class="pipeline-controls">
        <button class="btn btn--sm btn--outline" @click="refreshStatus">刷新状态</button>
      </div>
    </div>

    <div class="pipeline-container">
      <!-- 管道步骤 -->
      <div class="pipeline-steps">
        <div
          v-for="(step, index) in steps"
          :key="step.id"
          :class="['pipeline-step', `step--${step.status}`]"
        >
          <div class="step-icon">
            <span v-if="step.status === 'completed'">✓</span>
            <span v-else-if="step.status === 'running'">●</span>
            <span v-else-if="step.status === 'failed'">✗</span>
            <span v-else>○</span>
          </div>
          <div class="step-content">
            <div class="step-name">{{ step.name }}</div>
            <div class="step-description">{{ step.description }}</div>
            <div v-if="step.duration" class="step-duration">{{ step.duration }}</div>
          </div>
          <div v-if="index < steps.length - 1" class="step-connector">
            <div class="connector-line"></div>
          </div>
        </div>
      </div>

      <!-- 构建日志 -->
      <div class="build-log">
        <h4>构建日志</h4>
        <div class="log-container">
          <div v-for="(log, index) in logs" :key="index" :class="['log-entry', `log--${log.type}`]">
            <span class="log-time">{{ log.timestamp }}</span>
            <span class="log-message">{{ log.message }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 构建统计 -->
    <div class="build-stats">
      <div class="stat-item">
        <span class="stat-label">总大小</span>
        <span class="stat-value">{{ stats.totalSize }}</span>
      </div>
      <div class="stat-item">
        <span class="stat-label">规则包数</span>
        <span class="stat-value">{{ stats.rulepacks }}</span>
      </div>
      <div class="stat-item">
        <span class="stat-label">评分系统数</span>
        <span class="stat-value">{{ stats.scoringSystems }}</span>
      </div>
      <div class="stat-item">
        <span class="stat-label">构建时间</span>
        <span class="stat-value">{{ stats.buildTime }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">

interface PipelineStep {
  id: string
  name: string
  description: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  duration?: string
}

interface BuildLog {
  timestamp: string
  type: 'info' | 'warning' | 'error' | 'success'
  message: string
}

interface BuildStats {
  totalSize: string
  rulepacks: number
  scoringSystems: number
  buildTime: string
}

const props = defineProps<{
  steps: PipelineStep[]
  logs: BuildLog[]
  stats: BuildStats
}>()

const emit = defineEmits<{
  (e: 'refresh'): void
}>()

function refreshStatus() {
  emit('refresh')
}
</script>

<style scoped>
.offline-pipeline {
  display: flex;
  flex-direction: column;
  gap: 16px;
  background: var(--color-bg-surface);
  border-radius: 8px;
  border: 1px solid var(--color-border, #E3E7EC);
  padding: 16px;
}

.pipeline-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.pipeline-title {
  font-size: 16px;
  font-weight: 600;
  margin: 0;
}

.pipeline-container {
  display: flex;
  gap: 16px;
}

.pipeline-steps {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.pipeline-step {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px;
  background: var(--color-bg-surface-secondary);
  border-radius: 6px;
  position: relative;
}

.step--pending {
  opacity: 0.6;
}

.step--running {
  background: var(--color-primary-bg);
  border: 1px solid var(--color-primary);
}

.step--completed {
  background: var(--color-normal-bg);
  border: 1px solid var(--color-normal-border);
}

.step--failed {
  background: var(--color-critical-bg);
  border: 1px solid var(--color-critical-border);
}

.step-icon {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  font-size: 14px;
}

.step--pending .step-icon {
  background: var(--color-bg-inset);
  color: var(--color-text-tertiary);
}

.step--running .step-icon {
  background: var(--color-primary);
  color: var(--color-text-inverse);
}

.step--completed .step-icon {
  background: var(--color-success);
  color: var(--color-text-inverse);
}

.step--failed .step-icon {
  background: var(--color-danger);
  color: var(--color-text-inverse);
}

.step-content {
  flex: 1;
}

.step-name {
  font-weight: 600;
  font-size: 14px;
  margin-bottom: 4px;
}

.step-description {
  font-size: 12px;
  color: var(--color-text-secondary);
}

.step-duration {
  font-size: 11px;
  color: var(--color-text-tertiary);
  margin-top: 4px;
}

.step-connector {
  position: absolute;
  left: 23px;
  top: 100%;
  height: 8px;
  width: 2px;
  background: var(--color-bg-inset);
}

.build-log {
  width: 300px;
  background: var(--color-bg-surface-secondary);
  border-radius: 4px;
  padding: 12px;
}

.build-log h4 {
  margin: 0 0 12px;
  font-size: 14px;
  font-weight: 600;
}

.log-container {
  max-height: 300px;
  overflow-y: auto;
  font-family: monospace;
  font-size: 12px;
}

.log-entry {
  padding: 4px 0;
  border-bottom: 1px solid var(--color-border);
}

.log-time {
  color: var(--color-text-tertiary);
  margin-right: 8px;
}

.log--info .log-message { color: var(--color-text-primary); }
.log--warning .log-message { color: var(--color-warning); }
.log--error .log-message { color: var(--color-danger); }
.log--success .log-message { color: var(--color-success); }

.build-stats {
  display: flex;
  gap: 24px;
  padding: 12px;
  background: var(--color-bg-surface-secondary);
  border-radius: 4px;
}

.stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.stat-label {
  font-size: 12px;
  color: var(--color-text-secondary);
  margin-bottom: 4px;
}

.stat-value {
  font-size: 18px;
  font-weight: 600;
  color: var(--color-text-primary);
}
</style>
