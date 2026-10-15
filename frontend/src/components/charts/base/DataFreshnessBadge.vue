<template>
  <span class="freshness-badge" :class="[`freshness-badge--${status}`]">
    <SyncOutlined v-if="status === 'fresh'" spin />
    <ClockCircleOutlined v-else-if="status === 'stale'" />
    <DisconnectOutlined v-else />
    <span class="freshness-badge__text">{{ label }}</span>
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { SyncOutlined, ClockCircleOutlined, DisconnectOutlined } from '@ant-design/icons-vue'

const props = defineProps<{
  /** 最后更新时间（ISO字符串或时间戳） */
  updatedAt: string | number
  /** 新鲜阈值（秒），默认300（5分钟） */
  freshThreshold?: number
  /** 过期阈值（秒），默认1800（30分钟） */
  staleThreshold?: number
}>()

const freshMs = computed(() => (props.freshThreshold ?? 300) * 1000)
const staleMs = computed(() => (props.staleThreshold ?? 1800) * 1000)

const status = computed(() => {
  const diff = Date.now() - new Date(props.updatedAt).getTime()
  if (diff < freshMs.value) return 'fresh'
  if (diff < staleMs.value) return 'stale'
  return 'expired'
})

const label = computed(() => {
  const diff = Date.now() - new Date(props.updatedAt).getTime()
  if (diff < 60_000) return '刚刚更新'
  if (diff < 3600_000) return `${Math.floor(diff / 60_000)}分钟前`
  if (diff < 86400_000) return `${Math.floor(diff / 3600_000)}小时前`
  return `${Math.floor(diff / 86400_000)}天前`
})
</script>

<style scoped>
.freshness-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 500;
  white-space: nowrap;
}

.freshness-badge--fresh {
  background: var(--color-normal-bg);
  color: var(--color-normal);
}

.freshness-badge--stale {
  background: var(--color-warning-soft-bg);
  color: var(--color-warning-soft);
}

.freshness-badge--expired {
  background: var(--color-critical-bg);
  color: var(--color-danger);
}
</style>
