<template>
  <div class="brief-container">
    <div class="brief-toolbar">
      <h3 class="brief-title">📄 交班简报</h3>
      <a-segmented
        v-model:value="currentMode"
        :options="modeOptions"
        size="small"
        @change="emit('mode-change', currentMode)"
      />
    </div>

    <!-- Ward mode: one-liner cards -->
    <template v-if="brief.mode === 'ward'">
      <div class="ward-card">
        <div class="one-liner">{{ brief.one_liner }}</div>
        <div class="key-points">
          <a-tag v-for="(kp, i) in brief.key_points" :key="i" :color="kp.includes('危急') ? 'red' : 'blue'">
            {{ kp }}
          </a-tag>
        </div>
      </div>
    </template>

    <!-- Full / Compact mode: block list -->
    <template v-else>
      <div v-if="!brief.blocks?.length" class="empty-hint">暂无内容 — 请先生成交班草稿</div>
      <div
        v-for="(block, idx) in brief.blocks"
        :key="idx"
        class="brief-block"
        :class="{ urgent: block.urgent }"
      >
        <div class="block-header">
          <span class="block-icon">{{ block.icon }}</span>
          <span class="block-section">{{ block.section }}</span>
        </div>
        <div class="block-lines">
          <div v-for="(line, li) in block.lines" :key="li" class="block-line">{{ line }}</div>
        </div>
        <div v-if="block.tags?.length" class="block-tags">
          <a-tag v-for="(t, ti) in block.tags" :key="ti" size="small">{{ t }}</a-tag>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { Segmented as ASegmented, Tag as ATag } from 'ant-design-vue'
import type { HandoverBrief as BriefType } from '../../api/handover'

const props = defineProps<{
  brief: BriefType
}>()

const emit = defineEmits<{
  'mode-change': [mode: string]
}>()

const currentMode = ref<string>(props.brief.mode || 'full')
const modeOptions = [
  { label: '完整', value: 'full' },
  { label: '精简', value: 'compact' },
  { label: '大交班', value: 'ward' },
]
</script>

<style scoped>
.brief-container {
  padding: 12px 16px;
  background: var(--bg-surface);
  border-radius: var(--card-radius);
  border: 1px solid var(--border-color, #334155);
}
.brief-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.brief-title {
  margin: 0;
  font-size: 15px;
  color: var(--text-main);
}
.ward-card {
  padding: 12px;
  background: var(--bg-elevated, #1e293b);
  border-radius: 8px;
}
.one-liner {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-main);
  margin-bottom: 8px;
}
.key-points {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.brief-block {
  padding: 8px 0;
  border-bottom: 1px solid var(--border-color, #334155);
}
.brief-block.urgent {
  background: rgba(239, 68, 68, 0.08);
  border-left: 3px solid var(--danger, #ef4444);
  padding-left: 10px;
  border-radius: 4px;
}
.block-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}
.block-icon { font-size: 14px; }
.block-section {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-main);
}
.block-lines {
  padding-left: 22px;
}
.block-line {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.6;
}
.block-tags {
  padding-left: 22px;
  margin-top: 4px;
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}
.empty-hint {
  color: var(--text-secondary);
  font-size: 13px;
  text-align: center;
  padding: 24px 0;
}
</style>
