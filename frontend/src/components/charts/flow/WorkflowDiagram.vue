<template>
  <div class="workflow-diagram">
    <div v-if="title" class="workflow-diagram__header">
      <span class="workflow-diagram__title">{{ title }}</span>
      <span v-if="progressText" class="workflow-diagram__progress">{{ progressText }}</span>
    </div>

    <div class="workflow-diagram__body" :class="[`workflow-diagram__body--${direction}`]">
      <div
        v-for="(node, index) in nodes"
        :key="node.id"
        class="workflow-node"
        :class="[`workflow-node--${node.status}`, { 'workflow-node--clickable': !!node.route }]"
        @click="$emit('nodeClick', node)"
      >
        <div class="workflow-node__icon">
          <CheckCircleFilled v-if="node.status === 'completed'" />
          <LoadingOutlined v-if="node.status === 'running'" spin />
          <CloseCircleFilled v-if="node.status === 'failed'" />
          <ExclamationCircleFilled v-if="node.status === 'warning'" />
          <StopOutlined v-if="node.status === 'blocked'" />
          <MinusCircleOutlined v-if="node.status === 'skipped'" />
          <ClockCircleOutlined v-if="node.status === 'pending'" />
          <QuestionCircleOutlined v-if="node.status === 'unknown'" />
        </div>
        <div class="workflow-node__content">
          <div class="workflow-node__name">{{ node.name }}</div>
          <div v-if="node.assignee" class="workflow-node__assignee">{{ node.assignee }}</div>
          <div v-if="node.time" class="workflow-node__time">{{ node.time }}</div>
        </div>

        <!-- 连接线 -->
        <div v-if="index < nodes.length - 1" class="workflow-connector">
          <RightOutlined v-if="direction === 'horizontal'" />
          <DownOutlined v-else />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import {
  CheckCircleFilled, LoadingOutlined, CloseCircleFilled,
  ExclamationCircleFilled, StopOutlined, MinusCircleOutlined,
  ClockCircleOutlined, QuestionCircleOutlined,
  RightOutlined, DownOutlined,
} from '@ant-design/icons-vue'
import { type FlowNodeStatus } from '../../../styles/tokens/colors'

export interface WorkflowNode {
  id: string
  name: string
  status: FlowNodeStatus
  assignee?: string
  time?: string
  route?: string
  count?: number
}

const props = withDefaults(defineProps<{
  title?: string
  nodes: WorkflowNode[]
  direction?: 'horizontal' | 'vertical'
}>(), {
  direction: 'horizontal',
})

defineEmits<{ nodeClick: [WorkflowNode] }>()

const progressText = computed(() => {
  const total = props.nodes.length
  if (!total) return ''
  const completed = props.nodes.filter(n => n.status === 'completed').length
  return `${completed}/${total} 项`
})
</script>

<style scoped>
.workflow-diagram {
  background: var(--color-bg-surface, #fff);
  border: 1px solid var(--color-border, #DCE5EF);
  border-radius: 8px;
  padding: 16px;
}

.workflow-diagram__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.workflow-diagram__title {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary, #17233D);
}

.workflow-diagram__progress {
  font-size: 12px;
  color: var(--color-text-secondary, #667085);
  background: var(--color-bg-surface-secondary, #F1F3F5);
  padding: 2px 8px;
  border-radius: 100px;
}

.workflow-diagram__body--horizontal {
  display: flex;
  align-items: flex-start;
  gap: 0;
  overflow-x: auto;
  padding-bottom: 4px;
}

.workflow-diagram__body--vertical {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.workflow-node {
  position: relative;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 6px;
  border: 1px solid var(--color-border, #DCE5EF);
  background: var(--color-bg-surface, #fff);
  min-width: 100px;
  transition: all 0.2s;
}

.workflow-node--clickable { cursor: pointer; }
.workflow-node--clickable:hover { border-color: var(--color-primary, #1677FF); }

.workflow-node--completed { border-color: #12A66A; background: #E8F7F0; }
.workflow-node--running { border-color: #1677FF; background: #EAF4FF; }
.workflow-node--failed { border-color: #D92D20; background: #FEECEB; }
.workflow-node--warning { border-color: #F79009; background: #FFF3E0; }
.workflow-node--blocked { border-color: #D92D20; background: #FEECEB; }

.workflow-node__icon { font-size: 16px; flex-shrink: 0; }
.workflow-node--completed .workflow-node__icon { color: #12A66A; }
.workflow-node--running .workflow-node__icon { color: #1677FF; }
.workflow-node--failed .workflow-node__icon { color: #D92D20; }
.workflow-node--warning .workflow-node__icon { color: #F79009; }
.workflow-node--pending .workflow-node__icon { color: #8A94A6; }

.workflow-node__name {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text-primary, #17233D);
  white-space: nowrap;
}

.workflow-node__assignee {
  font-size: 11px;
  color: var(--color-text-tertiary, #8A94A6);
}

.workflow-node__time {
  font-size: 10px;
  color: var(--color-text-disabled, #B6BEC9);
}

.workflow-connector {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-border, #DCE5EF);
  font-size: 12px;
  flex-shrink: 0;
  padding: 0 4px;
}

.workflow-diagram__body--horizontal .workflow-connector {
  padding: 0 2px;
}

.workflow-diagram__body--vertical .workflow-connector {
  transform: rotate(0deg);
  padding: 2px 0;
}
</style>
