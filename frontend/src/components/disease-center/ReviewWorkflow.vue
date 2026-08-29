<template>
  <div class="review-workflow">
    <div class="workflow-header">
      <h3 class="workflow-title">审核流程</h3>
    </div>

    <div class="workflow-container">
      <!-- 流程步骤 -->
      <div class="workflow-steps">
        <div
          v-for="(step, index) in steps"
          :key="step.id"
          :class="['workflow-step', `step--${step.status}`]"
        >
          <div class="step-indicator">
            <div class="step-number">{{ index + 1 }}</div>
          </div>
          <div class="step-content">
            <div class="step-name">{{ step.name }}</div>
            <div class="step-description">{{ step.description }}</div>
            <div v-if="step.assignee" class="step-assignee">
              <span class="assignee-label">负责人:</span>
              <span class="assignee-name">{{ step.assignee }}</span>
            </div>
            <div v-if="step.completedAt" class="step-time">
              完成时间: {{ step.completedAt }}
            </div>
          </div>
          <div v-if="index < steps.length - 1" class="step-connector">
            <div class="connector-arrow">→</div>
          </div>
        </div>
      </div>

      <!-- 审核历史 -->
      <div class="review-history">
        <h4>审核历史</h4>
        <div class="history-list">
          <div v-for="(record, index) in history" :key="index" class="history-item">
            <div class="history-icon" :class="`icon--${record.action}`">
              <span v-if="record.action === 'approve'">✓</span>
              <span v-else-if="record.action === 'reject'">✗</span>
              <span v-else>●</span>
            </div>
            <div class="history-content">
              <div class="history-action">{{ getActionName(record.action) }}</div>
              <div class="history-user">{{ record.user }}</div>
              <div class="history-time">{{ record.timestamp }}</div>
              <div v-if="record.comment" class="history-comment">{{ record.comment }}</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 操作按钮 -->
    <div class="workflow-actions">
      <button
        v-if="canApprove"
        class="btn btn--sm btn--primary"
        @click="$emit('approve')"
      >
        通过审核
      </button>
      <button
        v-if="canReject"
        class="btn btn--sm btn--danger"
        @click="$emit('reject')"
      >
        拒绝审核
      </button>
      <button
        v-if="canSubmit"
        class="btn btn--sm btn--outline"
        @click="$emit('submit')"
      >
        提交审核
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface WorkflowStep {
  id: string
  name: string
  description: string
  status: 'pending' | 'active' | 'completed' | 'skipped'
  assignee?: string
  completedAt?: string
}

interface ReviewRecord {
  action: 'submit' | 'approve' | 'reject' | 'request_changes'
  user: string
  timestamp: string
  comment?: string
}

const props = defineProps<{
  steps: WorkflowStep[]
  history: ReviewRecord[]
  currentStatus: string
}>()

const emit = defineEmits<{
  (e: 'approve'): void
  (e: 'reject'): void
  (e: 'submit'): void
}>()

const canApprove = computed(() => {
  return ['review_pending', 'reviewing'].includes(props.currentStatus)
})

const canReject = computed(() => {
  return ['review_pending', 'reviewing'].includes(props.currentStatus)
})

const canSubmit = computed(() => {
  return ['draft', 'changes_requested'].includes(props.currentStatus)
})

function getActionName(action: string): string {
  const names: Record<string, string> = {
    submit: '提交审核',
    approve: '通过审核',
    reject: '拒绝审核',
    request_changes: '要求修改'
  }
  return names[action] || action
}
</script>

<style scoped>
.review-workflow {
  display: flex;
  flex-direction: column;
  gap: 16px;
  background: #fff;
  border-radius: 8px;
  border: 1px solid var(--color-border, #E3E7EC);
  padding: 16px;
}

.workflow-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.workflow-title {
  font-size: 16px;
  font-weight: 600;
  margin: 0;
}

.workflow-container {
  display: flex;
  gap: 24px;
}

.workflow-steps {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.workflow-step {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px;
  background: #f8f9fa;
  border-radius: 6px;
  position: relative;
}

.step--pending {
  opacity: 0.6;
}

.step--active {
  background: #e6f7ff;
  border: 1px solid #91d5ff;
}

.step--completed {
  background: #f6ffed;
  border: 1px solid #b7eb8f;
}

.step--skipped {
  opacity: 0.4;
}

.step-indicator {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.step-number {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  font-size: 12px;
  font-weight: 600;
}

.step--pending .step-number {
  background: #d9d9d9;
  color: #999;
}

.step--active .step-number {
  background: #1890ff;
  color: #fff;
}

.step--completed .step-number {
  background: #52c41a;
  color: #fff;
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
  color: #666;
  margin-bottom: 4px;
}

.step-assignee {
  font-size: 12px;
  color: #333;
}

.assignee-label {
  color: #999;
}

.step-time {
  font-size: 11px;
  color: #999;
  margin-top: 4px;
}

.step-connector {
  position: absolute;
  right: -16px;
  top: 50%;
  transform: translateY(-50%);
  color: #d9d9d9;
  font-size: 18px;
}

.review-history {
  width: 300px;
  background: #f8f9fa;
  border-radius: 4px;
  padding: 12px;
}

.review-history h4 {
  margin: 0 0 12px;
  font-size: 14px;
  font-weight: 600;
}

.history-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.history-item {
  display: flex;
  gap: 12px;
}

.history-icon {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  font-size: 12px;
}

.icon--approve {
  background: #52c41a;
  color: #fff;
}

.icon--reject {
  background: #ff4d4f;
  color: #fff;
}

.icon--submit,
.icon--request_changes {
  background: #1890ff;
  color: #fff;
}

.history-content {
  flex: 1;
}

.history-action {
  font-weight: 600;
  font-size: 13px;
}

.history-user {
  font-size: 12px;
  color: #666;
}

.history-time {
  font-size: 11px;
  color: #999;
}

.history-comment {
  margin-top: 4px;
  padding: 8px;
  background: #fff;
  border-radius: 4px;
  font-size: 12px;
  color: #333;
}

.workflow-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}
</style>
