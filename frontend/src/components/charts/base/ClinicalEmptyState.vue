<template>
  <div class="clinical-empty" :class="[`clinical-empty--${size}`]">
    <div class="clinical-empty__icon">
      <InboxOutlined v-if="type === 'no-data'" />
      <LoadingOutlined v-if="type === 'loading'" spin />
      <CloseCircleOutlined v-if="type === 'error'" />
      <FieldTimeOutlined v-if="type === 'expired'" />
      <WifiOutlined v-if="type === 'disconnected'" />
      <LockOutlined v-if="type === 'no-permission'" />
    </div>
    <div class="clinical-empty__text">{{ message }}</div>
    <div v-if="lastValidTime" class="clinical-empty__meta">
      最后有效数据: {{ lastValidTime }}
    </div>
    <div v-if="impact" class="clinical-empty__impact">
      {{ impact }}
    </div>
    <button
      v-if="actionText"
      class="clinical-empty__action"
      @click="$emit('action')"
    >
      {{ actionText }}
    </button>
  </div>
</template>

<script setup lang="ts">
import {
  InboxOutlined, LoadingOutlined, CloseCircleOutlined,
  FieldTimeOutlined, WifiOutlined, LockOutlined,
} from '@ant-design/icons-vue'

withDefaults(defineProps<{
  /** 空状态类型 */
  type?: 'no-data' | 'loading' | 'error' | 'expired' | 'disconnected' | 'no-permission'
  /** 提示信息 */
  message?: string
  /** 最后有效数据时间 */
  lastValidTime?: string
  /** 是否影响临床判断 */
  impact?: string
  /** 操作按钮文字 */
  actionText?: string
  /** 尺寸 */
  size?: 'small' | 'default' | 'large'
}>(), {
  type: 'no-data',
  size: 'default',
  message: '暂无数据',
})

defineEmits<{
  action: []
}>()
</script>

<style scoped>
.clinical-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 24px;
  color: var(--color-text-tertiary, #8A94A6);
  text-align: center;
}

.clinical-empty--small { padding: 12px; }
.clinical-empty--large { padding: 48px; }

.clinical-empty__icon {
  font-size: 32px;
  margin-bottom: 12px;
  opacity: 0.5;
}

.clinical-empty--small .clinical-empty__icon { font-size: 24px; margin-bottom: 8px; }
.clinical-empty--large .clinical-empty__icon { font-size: 48px; margin-bottom: 16px; }

.clinical-empty__text {
  font-size: 14px;
  line-height: 1.5;
  max-width: 280px;
}

.clinical-empty__meta {
  font-size: 12px;
  margin-top: 8px;
  color: var(--color-text-disabled, #B6BEC9);
}

.clinical-empty__impact {
  font-size: 12px;
  margin-top: 6px;
  color: var(--color-warning, #E5B700);
  font-weight: 500;
}

.clinical-empty__action {
  margin-top: 16px;
  padding: 6px 16px;
  border: 1px solid var(--color-border, #DCE5EF);
  border-radius: 6px;
  background: var(--color-bg-surface, #fff);
  color: var(--color-text-primary, #17233D);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}

.clinical-empty__action:hover {
  border-color: var(--color-primary, #1677FF);
  color: var(--color-primary, #1677FF);
}
</style>
