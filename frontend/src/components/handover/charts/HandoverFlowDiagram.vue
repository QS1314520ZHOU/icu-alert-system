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
.handover-flow { background: #fff; border-radius: 8px; border: 1px solid #DCE5EF; padding: 16px; }
.flow-header { margin-bottom: 12px; }
.flow-title { font-size: 14px; font-weight: 600; color: #17233D; margin: 0; }

.flow-steps { display: flex; align-items: flex-start; gap: 4px; overflow-x: auto; padding-bottom: 8px; }
.flow-step {
  display: flex; flex-direction: column; align-items: center; min-width: 80px;
  position: relative;
}
.step-dot {
  width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
  font-size: 12px; font-weight: 600; color: #fff; background: #98A2B3;
}
.flow-step--done .step-dot { background: #12A66A; }
.flow-step--current .step-dot { background: #2E90FA; box-shadow: 0 0 0 3px rgba(46,144,250,0.2); }
.flow-step--blocked .step-dot { background: #D92D20; }

.step-label { font-size: 11px; color: #17233D; margin-top: 4px; text-align: center; }
.step-meta { font-size: 10px; color: #5F6B7A; }
.step-time { font-size: 10px; color: #8A94A6; }
.step-blocked { font-size: 10px; color: #D92D20; font-weight: 500; }

.step-arrow {
  position: absolute; right: -12px; top: 10px; color: #98A2B3; font-size: 14px;
}

.flow-caption { font-size: 12px; color: #8A94A6; margin-top: 12px; border-top: 1px solid #F0F3F7; padding-top: 8px; }
</style>
