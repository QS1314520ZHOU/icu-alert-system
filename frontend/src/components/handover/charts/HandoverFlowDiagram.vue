<template>
  <div class="handover-flow">
    <div class="flow-header">
      <h3 class="flow-title">交班流程</h3>
    </div>
    <div class="flow-steps">
      <div
        v-for="(step, i) in steps"
        :key="step.key"
        class="flow-step"
        :class="stepClass(step)"
      >
        <div class="step-dot">{{ i + 1 }}</div>
        <div class="step-label">{{ step.label }}</div>
        <div v-if="step.operator" class="step-meta">{{ step.operator }}</div>
        <div v-if="step.time" class="step-time">{{ step.time }}</div>
        <div v-if="step.blocked" class="step-blocked">{{ step.blocked }}</div>
        <div v-if="i < steps.length - 1" class="step-arrow">→</div>
      </div>
    </div>
    <div class="flow-caption">
      显示当前交班文档的流程节点状态、操作者和时间。阻塞原因标红显示。
    </div>
  </div>
</template>

<script setup lang="ts">
interface FlowStep {
  key: string
  label: string
  status: 'done' | 'current' | 'pending' | 'blocked'
  operator?: string
  time?: string
  blocked?: string
}

defineProps<{ steps: FlowStep[] }>()

function stepClass(step: FlowStep) {
  return `flow-step--${step.status}`
}
</script>

<style scoped>
.handover-flow { background: var(--color-bg-surface); border-radius: var(--radius-lg); border: 1px solid var(--color-border); padding: 16px; }
.flow-header { margin-bottom: 12px; }
.flow-title { font-size: 14px; font-weight: 600; color: var(--color-text-primary); margin: 0; }

.flow-steps { display: flex; align-items: flex-start; gap: 4px; overflow-x: auto; padding-bottom: 8px; }
.flow-step {
  display: flex; flex-direction: column; align-items: center; min-width: 80px;
  position: relative;
}
.step-dot {
  width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
  font-size: 12px; font-weight: 600; color: var(--color-bg-surface); background: var(--color-unknown);
}
.flow-step--done .step-dot { background: var(--color-normal); }
.flow-step--current .step-dot { background: var(--color-info); box-shadow: 0 0 0 3px var(--color-info-bg); }
.flow-step--blocked .step-dot { background: var(--color-danger); }

.step-label { font-size: 11px; color: var(--color-text-primary); margin-top: 4px; text-align: center; }
.step-meta { font-size: 10px; color: var(--color-text-secondary); }
.step-time { font-size: 10px; color: var(--color-text-tertiary); }
.step-blocked { font-size: 10px; color: var(--color-danger); font-weight: 500; }

.step-arrow {
  position: absolute; right: -12px; top: 10px; color: var(--color-unknown); font-size: 14px;
}

.flow-caption { font-size: 12px; color: var(--color-text-tertiary); margin-top: 12px; border-top: 1px solid var(--color-divider); padding-top: 8px; }
</style>
