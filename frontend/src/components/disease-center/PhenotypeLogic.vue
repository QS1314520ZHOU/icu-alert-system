<template>
  <div class="phenotype-logic">
    <div class="logic-header">
      <h3 class="logic-title">表型逻辑编辑器</h3>
      <div class="logic-controls">
        <button class="btn btn--sm btn--outline" @click="addNode">添加节点</button>
        <button class="btn btn--sm btn--outline" @click="validateLogic">验证逻辑</button>
        <button class="btn btn--sm btn--primary" @click="saveLogic">保存</button>
      </div>
    </div>

    <div class="logic-container">
      <!-- 逻辑画布 -->
      <div class="logic-canvas">
        <div v-for="(node, index) in nodes" :key="node.id" class="logic-node">
          <div :class="['node-card', `node-card--${node.operator}`]">
            <div class="node-header">
              <span class="node-operator">{{ node.operator }}</span>
              <button class="btn btn--xs btn--ghost" @click="removeNode(index)">×</button>
            </div>
            <div class="node-body">
              <div v-for="(_input, inputIndex) in node.inputs" :key="inputIndex" class="node-input">
                <input
                  v-model="node.inputs[inputIndex]"
                  class="form-input"
                  placeholder="输入变量"
                />
                <button class="btn btn--xs btn--ghost" @click="removeInput(node, inputIndex)">×</button>
              </div>
              <button class="btn btn--xs btn--outline" @click="addInput(node)">+ 添加输入</button>
            </div>
            <div class="node-footer">
              <span class="node-output">→ {{ node.output }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 验证结果 -->
      <div v-if="validationResult" class="validation-result">
        <div :class="['validation-status', validationResult.valid ? 'valid' : 'invalid']">
          {{ validationResult.valid ? '✓ 逻辑有效' : '✗ 逻辑无效' }}
        </div>
        <div v-if="validationResult.errors.length" class="validation-errors">
          <div v-for="(error, index) in validationResult.errors" :key="index" class="error-item">
            {{ error }}
          </div>
        </div>
        <div v-if="validationResult.warnings.length" class="validation-warnings">
          <div v-for="(warning, index) in validationResult.warnings" :key="index" class="warning-item">
            {{ warning }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

interface LogicNode {
  id: string
  operator: 'AND' | 'OR' | 'NOT' | 'gt' | 'lt' | 'gte' | 'lte' | 'eq' | 'neq' | 'in' | 'between'
  inputs: string[]
  output: string
}

interface ValidationResult {
  valid: boolean
  errors: string[]
  warnings: string[]
}

const props = defineProps<{
  nodes: LogicNode[]
}>()

const emit = defineEmits<{
  (e: 'update:nodes', nodes: LogicNode[]): void
  (e: 'validate'): void
  (e: 'save'): void
}>()

const validationResult = ref<ValidationResult | null>(null)

function addNode() {
  const newNode: LogicNode = {
    id: `node-${Date.now()}`,
    operator: 'AND',
    inputs: [],
    output: `result_${props.nodes.length}`
  }
  emit('update:nodes', [...props.nodes, newNode])
}

function removeNode(index: number) {
  const newNodes = [...props.nodes]
  newNodes.splice(index, 1)
  emit('update:nodes', newNodes)
}

function addInput(node: LogicNode) {
  node.inputs.push('')
}

function removeInput(node: LogicNode, index: number) {
  node.inputs.splice(index, 1)
}

function validateLogic() {
  const errors: string[] = []
  const warnings: string[] = []

  props.nodes.forEach((node, index) => {
    if (!node.inputs.length) {
      errors.push(`节点 ${index + 1}: 缺少输入`)
    }
    if (!node.output) {
      errors.push(`节点 ${index + 1}: 缺少输出`)
    }
    if (['gt', 'lt', 'gte', 'lte', 'eq', 'neq'].includes(node.operator) && node.inputs.length !== 2) {
      errors.push(`节点 ${index + 1}: ${node.operator} 运算符需要恰好 2 个输入`)
    }
    if (node.operator === 'NOT' && node.inputs.length !== 1) {
      errors.push(`节点 ${index + 1}: NOT 运算符需要恰好 1 个输入`)
    }
  })

  validationResult.value = {
    valid: errors.length === 0,
    errors,
    warnings
  }

  emit('validate')
}

function saveLogic() {
  emit('save')
}
</script>

<style scoped>
.phenotype-logic {
  display: flex;
  flex-direction: column;
  gap: 16px;
  background: var(--color-bg-surface);
  border-radius: 8px;
  border: 1px solid var(--color-border, #E3E7EC);
  padding: 16px;
}

.logic-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.logic-title {
  font-size: 16px;
  font-weight: 600;
  margin: 0;
}

.logic-controls {
  display: flex;
  gap: 8px;
}

.logic-container {
  display: flex;
  gap: 16px;
}

.logic-canvas {
  flex: 1;
  min-height: 300px;
  background: var(--color-bg-surface-secondary);
  border-radius: 4px;
  padding: 16px;
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-content: flex-start;
}

.logic-node {
  width: 200px;
}

.node-card {
  background: var(--color-bg-surface);
  border-radius: 6px;
  border: 2px solid var(--color-border);
  overflow: hidden;
}

.node-card--AND { border-color: var(--color-primary); }
.node-card--OR { border-color: var(--color-success); }
.node-card--NOT { border-color: var(--color-danger); }
.node-card--gt,
.node-card--lt,
.node-card--gte,
.node-card--lte { border-color: var(--color-warning); }
.node-card--eq,
.node-card--neq { border-color: var(--color-ai); }

.node-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: var(--color-bg-surface-secondary);
  border-bottom: 1px solid var(--color-border);
}

.node-operator {
  font-weight: 600;
  font-size: 14px;
}

.node-body {
  padding: 12px;
}

.node-input {
  display: flex;
  gap: 4px;
  margin-bottom: 8px;
}

.node-input .form-input {
  flex: 1;
  padding: 6px 8px;
  border: 1px solid var(--color-border);
  border-radius: 4px;
  font-size: 12px;
}

.node-footer {
  padding: 8px 12px;
  background: var(--color-bg-surface-secondary);
  border-top: 1px solid var(--color-border);
}

.node-output {
  font-size: 12px;
  color: var(--color-text-secondary);
}

.validation-result {
  width: 280px;
  padding: 16px;
  background: var(--color-bg-surface-secondary);
  border-radius: 4px;
}

.validation-status {
  padding: 8px 12px;
  border-radius: 4px;
  font-weight: 600;
  margin-bottom: 12px;
}

.validation-status.valid {
  background: var(--color-normal-bg);
  color: var(--color-success);
}

.validation-status.invalid {
  background: var(--color-critical-bg);
  color: var(--color-danger);
}

.validation-errors,
.validation-warnings {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.error-item,
.warning-item {
  padding: 8px;
  border-radius: 4px;
  font-size: 13px;
}

.error-item {
  background: var(--color-critical-bg);
  color: var(--color-danger);
}

.warning-item {
  background: var(--color-warning-soft-bg);
  color: var(--color-warning);
}
</style>
