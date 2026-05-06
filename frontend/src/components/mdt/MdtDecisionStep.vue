<template>
  <a-card :bordered="false" class="mdt-step-card">
    <div class="step-card__head">
      <div>
        <span class="step-kicker">第三步</span>
        <h2>决议确认与闭环</h2>
        <p>AI 生成内容仅为待审核建议草案，不能作为医嘱直接执行；必须由执业医生结合床旁情况确认。</p>
      </div>
      <a-button type="primary" :disabled="isSessionClosed" :loading="savingWorkspace" @click="$emit('save')">保存决议</a-button>
    </div>

    <section class="decision-metrics">
      <article><span>待医生确认</span><strong>{{ pendingConfirmationCount }}</strong></article>
      <article><span>确认后待执行</span><strong>{{ pendingDecisionCount }}</strong></article>
      <article><span>进行中</span><strong>{{ inProgressDecisionCount }}</strong></article>
      <article><span>已完成</span><strong>{{ completedDecisionCount }}</strong></article>
      <article><span>已取消</span><strong>{{ dismissedDecisionCount }}</strong></article>
    </section>

    <div class="decision-list">
      <article v-for="(item, index) in decisionRows" :key="item.id || index" :class="['decision-item', `is-${item.status || 'pending_confirmation'}`]">
        <div class="decision-item__head">
          <strong>决议 {{ index + 1 }}</strong>
          <span>{{ decisionStatusLabel(item.status) }}</span>
        </div>
        <textarea v-model="item.action" class="field-textarea" :disabled="isSessionClosed" rows="3" placeholder="输入 MDT 决议动作"></textarea>
        <div class="decision-form-grid">
          <input v-model="item.owner" class="field-input" :disabled="isSessionClosed" placeholder="负责人" />
          <input v-model="item.deadline" class="field-input" :disabled="isSessionClosed" placeholder="执行时限" />
          <input v-model="item.monitoring" class="field-input" :disabled="isSessionClosed" placeholder="监测指标" />
          <input v-model="item.review_time" class="field-input" :disabled="isSessionClosed" placeholder="复评时间" />
          <select v-model="item.status" class="field-input" :disabled="isSessionClosed">
            <option value="pending_confirmation">待医生确认</option>
            <option value="doctor_confirmed">医生已确认</option>
            <option value="pending">确认后待执行</option>
            <option value="in_progress">进行中</option>
            <option value="completed">已完成</option>
            <option value="rejected">医生不采纳</option>
            <option value="needs_revision">需修改</option>
            <option value="dismissed">已取消</option>
          </select>
        </div>
        <textarea v-model="item.note" class="field-textarea" :disabled="isSessionClosed" rows="2" placeholder="医生意见 / 修改原因 / 闭环说明"></textarea>
        <div v-if="item.requires_confirmation !== false" class="decision-safety">
          AI 决议草案确认前不能转为正式医嘱或执行任务。
        </div>
        <div class="decision-actions">
          <a-button
            v-if="needsDoctorConfirmation(item)"
            size="small"
            type="primary"
            :disabled="isSessionClosed || confirmingDecisionIds.has(item.id)"
            @click="$emit('confirm', item, 'confirm')"
          >
            医生确认
          </a-button>
          <a-button
            v-if="needsDoctorConfirmation(item)"
            size="small"
            :disabled="isSessionClosed || confirmingDecisionIds.has(item.id)"
            @click="$emit('confirm', item, 'reject')"
          >
            不采纳
          </a-button>
          <a-button
            v-if="needsDoctorConfirmation(item)"
            size="small"
            :disabled="isSessionClosed || confirmingDecisionIds.has(item.id)"
            @click="$emit('confirm', item, 'revise')"
          >
            需修改
          </a-button>
          <a-button
            v-if="!needsDoctorConfirmation(item) && String(item.status || '') !== 'completed'"
            size="small"
            :disabled="isSessionClosed"
            @click="$emit('mark-status', item.id, 'completed')"
          >
            标记完成
          </a-button>
          <a-button size="small" danger :disabled="isSessionClosed" @click="$emit('remove', item.id)">删除</a-button>
        </div>
      </article>
    </div>

    <div class="step-actions">
      <a-button :disabled="isSessionClosed" @click="$emit('fill-defaults')">补全字段</a-button>
      <a-button :disabled="isSessionClosed" @click="$emit('add')">新增决议</a-button>
      <a-button type="primary" :loading="savingWorkspace" :disabled="isSessionClosed" @click="$emit('save')">保存决议</a-button>
      <a-popconfirm
        v-if="pendingConfirmationCount > 0"
        title="仍有决议未经过医生确认，建议确认后再归档。是否继续？"
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
    pending_confirmation: '待医生确认',
    doctor_confirmed: '医生已确认',
    pending: '确认后待执行',
    in_progress: '进行中',
    completed: '已完成',
    rejected: '医生不采纳',
    needs_revision: '需修改',
    dismissed: '已取消',
    draft: '草稿',
  } as Record<string, string>)[String(status || 'pending_confirmation').toLowerCase()] || '待医生确认'
}
</script>

<style scoped>
.mdt-step-card {
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 12px;
  background: rgba(15, 23, 42, 0.66);
}
.step-card__head,
.decision-item__head,
.decision-actions,
.step-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.step-kicker {
  color: rgba(125, 211, 252, 0.86);
  font-size: 12px;
  font-weight: 700;
}
h2 {
  margin: 4px 0 6px;
  color: #f8fafc;
}
p {
  margin: 0;
  color: #fed7aa;
  line-height: 1.55;
}
.decision-metrics {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 10px;
  margin: 16px 0;
}
.decision-metrics article {
  padding: 12px;
  border-radius: 10px;
  background: rgba(2, 6, 23, 0.3);
}
.decision-metrics span {
  color: rgba(148, 163, 184, 0.82);
}
.decision-metrics strong {
  display: block;
  margin-top: 4px;
  color: #f8fafc;
  font-size: 22px;
}
.decision-list {
  display: grid;
  gap: 12px;
}
.decision-item {
  padding: 14px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 10px;
  background: rgba(2, 6, 23, 0.28);
}
.decision-item.is-pending_confirmation,
.decision-item.is-needs_revision {
  border-color: rgba(251, 146, 60, 0.4);
}
.decision-item.is-completed {
  border-color: rgba(34, 197, 94, 0.38);
}
.decision-item__head {
  margin-bottom: 10px;
  color: #f8fafc;
}
.decision-item__head span {
  padding: 4px 9px;
  border-radius: 999px;
  color: #cbd5e1;
  background: rgba(30, 41, 59, 0.82);
}
.decision-form-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 8px;
  margin: 8px 0;
}
.field-input,
.field-textarea {
  width: 100%;
  border: 1px solid rgba(148, 163, 184, 0.24);
  border-radius: 8px;
  padding: 10px 12px;
  color: #f8fafc;
  background: rgba(15, 23, 42, 0.92);
}
.decision-safety {
  margin: 8px 0;
  color: #fed7aa;
  font-size: 13px;
}
.decision-actions {
  justify-content: flex-end;
  flex-wrap: wrap;
}
.step-actions {
  justify-content: flex-end;
  margin-top: 16px;
  flex-wrap: wrap;
}
@media (max-width: 1100px) {
  .decision-metrics,
  .decision-form-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

:global(html[data-theme='light']) .mdt-step-card,
:global(html[data-theme='light']) .decision-item {
  border-color: #dbeafe;
  background: #ffffff;
  box-shadow: 0 12px 30px rgba(15, 23, 42, 0.06);
}
:global(html[data-theme='light']) .step-kicker {
  color: #0284c7;
}
:global(html[data-theme='light']) h2,
:global(html[data-theme='light']) .decision-metrics strong,
:global(html[data-theme='light']) .decision-item__head {
  color: #0f172a;
}
:global(html[data-theme='light']) p,
:global(html[data-theme='light']) .decision-metrics span {
  color: #475569;
}
:global(html[data-theme='light']) .decision-metrics article,
:global(html[data-theme='light']) .decision-item__head span {
  background: #f1f5f9;
}
:global(html[data-theme='light']) .decision-item__head span {
  color: #334155;
}
:global(html[data-theme='light']) .field-input,
:global(html[data-theme='light']) .field-textarea {
  color: #0f172a;
  border-color: #cbd5e1;
  background: #ffffff;
}
:global(html[data-theme='light']) .field-input::placeholder,
:global(html[data-theme='light']) .field-textarea::placeholder {
  color: #94a3b8;
}
:global(html[data-theme='light']) .decision-safety {
  color: #9a3412;
}
</style>
