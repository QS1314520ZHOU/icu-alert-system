<template>
  <a-card :bordered="false" class="mdt-step-card">
    <div class="step-card__head">
      <div>
        <span class="step-kicker">第三步</span>
        <h2>决议确认</h2>
        <p class="step-hint">AI 建议需医生确认后才能执行。</p>
      </div>
      <div class="step-card__head-actions">
        <a-button :disabled="isSessionClosed" @click="$emit('add')">新增决议</a-button>
        <a-button type="primary" :loading="savingWorkspace" :disabled="isSessionClosed" @click="$emit('save')">保存</a-button>
      </div>
    </div>

    <!-- 决议统计条 -->
    <div class="decision-stats">
      <span class="stat-item">
        <b>{{ pendingConfirmationCount }}</b> 待确认
      </span>
      <span class="stat-item">
        <b>{{ pendingDecisionCount }}</b> 待执行
      </span>
      <span class="stat-item">
        <b>{{ inProgressDecisionCount }}</b> 进行中
      </span>
      <span class="stat-item is-done">
        <b>{{ completedDecisionCount }}</b> 已完成
      </span>
    </div>

    <!-- 决议列表 -->
    <div class="decision-list">
      <article
        v-for="(item, index) in decisionRows"
        :key="item.id || index"
        :class="['decision-card', `status-${item.status || 'pending_confirmation'}`]"
      >
        <div class="decision-card__header">
          <div class="decision-card__title">
            <strong>{{ item.action || '待补充决议内容' }}</strong>
            <span :class="['status-tag', `status-${item.status || 'pending_confirmation'}`]">
              {{ decisionStatusLabel(item.status) }}
            </span>
          </div>
        </div>

        <div class="decision-card__fields">
          <div class="field-item">
            <span class="field-label">负责人</span>
            <input v-model="item.owner" class="field-input" :disabled="isSessionClosed" placeholder="负责人" />
          </div>
          <div class="field-item">
            <span class="field-label">执行时限</span>
            <input v-model="item.deadline" class="field-input" :disabled="isSessionClosed" placeholder="时限" />
          </div>
          <div class="field-item">
            <span class="field-label">监测指标</span>
            <input v-model="item.monitoring" class="field-input" :disabled="isSessionClosed" placeholder="指标" />
          </div>
          <div class="field-item">
            <span class="field-label">复评时间</span>
            <input v-model="item.review_time" class="field-input" :disabled="isSessionClosed" placeholder="复评" />
          </div>
        </div>

        <textarea
          v-model="item.action"
          class="field-textarea"
          :disabled="isSessionClosed"
          rows="2"
          placeholder="决议内容"
        ></textarea>

        <div class="decision-card__actions">
          <template v-if="needsDoctorConfirmation(item)">
            <a-button size="small" type="primary" :disabled="isSessionClosed || confirmingDecisionIds.has(item.id)" @click="$emit('confirm', item, 'confirm')">
              确认
            </a-button>
            <a-button size="small" :disabled="isSessionClosed || confirmingDecisionIds.has(item.id)" @click="$emit('confirm', item, 'reject')">
              不采纳
            </a-button>
            <a-button size="small" :disabled="isSessionClosed || confirmingDecisionIds.has(item.id)" @click="$emit('confirm', item, 'revise')">
              需修改
            </a-button>
          </template>
          <template v-else-if="String(item.status || '') !== 'completed'">
            <a-button size="small" :disabled="isSessionClosed" @click="$emit('mark-status', item.id, 'completed')">
              标记完成
            </a-button>
          </template>
          <a-button size="small" danger :disabled="isSessionClosed" @click="$emit('remove', item.id)">删除</a-button>
        </div>
      </article>
    </div>

    <!-- 底部操作 -->
    <div class="step-actions">
      <a-button :disabled="isSessionClosed" @click="$emit('fill-defaults')">补全字段</a-button>
      <a-popconfirm
        v-if="pendingConfirmationCount > 0"
        title="仍有决议未确认，建议确认后再归档。是否继续？"
        @confirm="$emit('next')"
      >
        <a-button>进入文书归档</a-button>
      </a-popconfirm>
      <a-button v-else type="primary" @click="$emit('next')">进入文书归档</a-button>
    </div>
  </a-card>
</template>

<script setup lang="ts">
import { Button as AButton, Card as ACard, Popconfirm as APopconfirm } from 'ant-design-vue'

defineProps<{
  decisionRows: any[]
  pendingConfirmationCount: number
  pendingDecisionCount: number
  inProgressDecisionCount: number
  completedDecisionCount: number
  dismissedDecisionCount: number
  savingWorkspace: boolean
  isSessionClosed: boolean
  confirmingDecisionIds: Set<string>
}>()

defineEmits<{
  (event: 'add'): void
  (event: 'save'): void
  (event: 'fill-defaults'): void
  (event: 'confirm', row: any, action: 'confirm' | 'reject' | 'revise'): void
  (event: 'mark-status', id: string, status: 'completed'): void
  (event: 'remove', id: string): void
  (event: 'next'): void
}>()

void AButton
void ACard
void APopconfirm

function needsDoctorConfirmation(item: any) {
  const status = String(item?.status || 'pending_confirmation').toLowerCase()
  const confirmationStatus = String(item?.confirmation_status || '').toLowerCase()
  const confirmed = Boolean(item?.confirmed_at) || confirmationStatus === 'confirmed' || status === 'doctor_confirmed' || item?.requires_confirmation === false
  if (confirmed) return false
  if (confirmationStatus === 'rejected') return false
  return ['pending_confirmation', 'needs_revision'].includes(status) || item?.requires_confirmation !== false
}

function decisionStatusLabel(status: any) {
  return ({
    pending_confirmation: '待确认', doctor_confirmed: '已确认', pending: '待执行',
    in_progress: '进行中', completed: '已完成', rejected: '不采纳',
    needs_revision: '需修改', dismissed: '已取消', draft: '草稿',
  } as Record<string, string>)[String(status || 'pending_confirmation').toLowerCase()] || '待确认'
}
</script>

<style scoped>
.mdt-step-card {
  border: 1px solid var(--border-color);
  border-radius: var(--card-radius);
  background: var(--bg-surface);
}
.step-card__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
}
.step-card__head-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}
.step-kicker {
  color: var(--brand);
  font-size: 12px;
  font-weight: 700;
}
h2 {
  margin: 4px 0 0;
  color: var(--text-primary);
  font-size: 18px;
}
.step-hint {
  margin: 4px 0 0;
  color: var(--text-secondary);
  font-size: 12px;
}

/* 统计条 */
.decision-stats {
  display: flex;
  gap: 16px;
  margin-top: 14px;
  padding: 10px 14px;
  border: 1px solid var(--border-color);
  border-radius: var(--card-radius);
  background: var(--bg-surface);
}
.stat-item {
  color: var(--text-secondary);
  font-size: 13px;
}
.stat-item b {
  color: var(--text-primary);
  font-weight: 700;
  margin-right: 2px;
}
.stat-item.is-done b {
  color: #10b981;
}

/* 决议列表 */
.decision-list {
  display: grid;
  gap: 10px;
  margin-top: 14px;
}
.decision-card {
  padding: 14px;
  border: 1px solid var(--border-color);
  border-radius: var(--card-radius);
  background: var(--bg-surface);
}
.decision-card.status-pending_confirmation,
.decision-card.status-needs_revision {
  border-left: 3px solid #f59e0b;
}
.decision-card.status-completed {
  border-left: 3px solid #10b981;
}
.decision-card.status-doctor_confirmed,
.decision-card.status-pending {
  border-left: 3px solid #3b82f6;
}
.decision-card__header {
  margin-bottom: 10px;
}
.decision-card__title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}
.decision-card__title strong {
  color: var(--text-primary);
  font-size: 14px;
  line-height: 1.5;
}
.status-tag {
  display: inline-flex;
  align-items: center;
  height: 22px;
  padding: 0 8px;
  border-radius: var(--card-radius);
  font-size: 11px;
  font-weight: 600;
  flex-shrink: 0;
}
.status-tag.status-pending_confirmation { background: rgba(245, 158, 11, 0.1); color: #f59e0b; }
.status-tag.status-doctor_confirmed { background: rgba(59, 130, 246, 0.1); color: #3b82f6; }
.status-tag.status-pending { background: rgba(59, 130, 246, 0.1); color: #3b82f6; }
.status-tag.status-in_progress { background: rgba(139, 92, 246, 0.1); color: #8b5cf6; }
.status-tag.status-completed { background: rgba(16, 185, 129, 0.1); color: #10b981; }
.status-tag.status-rejected { background: rgba(239, 68, 68, 0.1); color: #ef4444; }
.status-tag.status-needs_revision { background: rgba(245, 158, 11, 0.1); color: #f59e0b; }
.status-tag.status-dismissed { background: rgba(107, 114, 128, 0.1); color: #6b7280; }

/* 字段 */
.decision-card__fields {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 8px;
}
.field-item {
  display: grid;
  gap: 2px;
}
.field-label {
  color: var(--text-secondary);
  font-size: 11px;
}
.field-input {
  width: 100%;
  min-height: 32px;
  padding: 4px 8px;
  border: 1px solid var(--border-color);
  border-radius: var(--card-radius);
  color: var(--text-primary);
  background: var(--bg-surface);
  font-size: 13px;
}
.field-input:disabled {
  opacity: 0.6;
}
.field-textarea {
  width: 100%;
  padding: 8px 10px;
  border: 1px solid var(--border-color);
  border-radius: var(--card-radius);
  color: var(--text-primary);
  background: var(--bg-surface);
  font-size: 13px;
  line-height: 1.5;
  resize: vertical;
}
.field-textarea:disabled {
  opacity: 0.6;
}

/* 操作 */
.decision-card__actions {
  display: flex;
  gap: 6px;
  justify-content: flex-end;
  margin-top: 10px;
}
.step-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 16px;
}

@media (max-width: 980px) {
  .decision-stats {
    flex-wrap: wrap;
    gap: 10px;
  }
  .decision-card__fields {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
