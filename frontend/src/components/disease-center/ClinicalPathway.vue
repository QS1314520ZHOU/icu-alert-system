<template>
  <div class="clinical-pathway">
    <div class="pathway-header">
      <h3 class="pathway-title">临床路径</h3>
      <div class="pathway-controls">
        <button class="btn btn--sm btn--outline" @click="addNode">添加节点</button>
        <button class="btn btn--sm btn--primary" @click="savePathway">保存路径</button>
      </div>
    </div>

    <div class="pathway-container">
      <!-- 路径画布 -->
      <div class="pathway-canvas" ref="canvas">
        <svg :width="canvasWidth" :height="canvasHeight">
          <!-- 连接线 -->
          <g class="edges">
            <path
              v-for="edge in edges"
              :key="edge.id"
              :d="getEdgePath(edge)"
              fill="none"
              :stroke="edge.color || '#999'"
              stroke-width="2"
              marker-end="url(#arrowhead)"
            />
          </g>

          <!-- 节点 -->
          <g class="nodes">
            <g
              v-for="node in nodes"
              :key="node.id"
              :transform="`translate(${node.x}, ${node.y})`"
              class="node"
              @click="selectNode(node)"
              @mousedown="startDrag(node, $event)"
            >
              <rect
                :width="nodeWidth"
                :height="nodeHeight"
                :rx="8"
                :fill="getNodeColor(node.type)"
                :stroke="selectedNode?.id === node.id ? '#333' : 'transparent'"
                stroke-width="2"
              />
              <text
                x="50%"
                y="50%"
                text-anchor="middle"
                dominant-baseline="middle"
                fill="#fff"
                font-size="12"
              >
                {{ node.label }}
              </text>
            </g>
          </g>
        </svg>
      </div>

      <!-- 节点编辑面板 -->
      <div v-if="selectedNode" class="node-editor">
        <h4>节点属性</h4>
        <div class="form-group">
          <label>节点名称</label>
          <input v-model="selectedNode.label" class="form-input" />
        </div>
        <div class="form-group">
          <label>节点类型</label>
          <select v-model="selectedNode.type" class="form-select">
            <option value="start">开始</option>
            <option value="task">任务</option>
            <option value="decision">决策</option>
            <option value="end">结束</option>
          </select>
        </div>
        <div class="form-group">
          <label>配置</label>
          <textarea v-model="configJson" class="form-textarea" rows="4"></textarea>
        </div>
        <div class="editor-actions">
          <button class="btn btn--sm btn--danger" @click="deleteNode">删除节点</button>
          <button class="btn btn--sm btn--outline" @click="addEdge">添加连接</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'

interface PathwayNode {
  id: string
  type: 'start' | 'task' | 'decision' | 'end'
  label: string
  x: number
  y: number
  config?: Record<string, any>
}

interface PathwayEdge {
  id: string
  source: string
  target: string
  condition?: string
  color?: string
}

const props = defineProps<{
  nodes: PathwayNode[]
  edges: PathwayEdge[]
}>()

const emit = defineEmits<{
  (e: 'update:nodes', nodes: PathwayNode[]): void
  (e: 'update:edges', edges: PathwayEdge[]): void
  (e: 'save'): void
}>()

const canvas = ref<HTMLElement | null>(null)
const canvasWidth = ref(800)
const canvasHeight = ref(600)
const nodeWidth = 120
const nodeHeight = 40
const selectedNode = ref<PathwayNode | null>(null)
const isDragging = ref(false)
const dragOffset = ref({ x: 0, y: 0 })

const configJson = computed({
  get: () => selectedNode.value ? JSON.stringify(selectedNode.value.config || {}, null, 2) : '{}',
  set: (val: string) => {
    if (selectedNode.value) {
      try {
        selectedNode.value.config = JSON.parse(val)
      } catch (e) {
        // 忽略无效 JSON
      }
    }
  }
})

function getNodeColor(type: string): string {
  const colors: Record<string, string> = {
    start: '#52c41a',
    task: '#1890ff',
    decision: '#faad14',
    end: '#ff4d4f'
  }
  return colors[type] || '#666'
}

function getEdgePath(edge: PathwayEdge): string {
  const source = props.nodes.find(n => n.id === edge.source)
  const target = props.nodes.find(n => n.id === edge.target)
  if (!source || !target) return ''

  const sx = source.x + nodeWidth / 2
  const sy = source.y + nodeHeight
  const tx = target.x + nodeWidth / 2
  const ty = target.y

  return `M ${sx} ${sy} C ${sx} ${(sy + ty) / 2}, ${tx} ${(sy + ty) / 2}, ${tx} ${ty}`
}

function selectNode(node: PathwayNode) {
  selectedNode.value = node
}

function startDrag(node: PathwayNode, event: MouseEvent) {
  isDragging.value = true
  dragOffset.value = {
    x: event.clientX - node.x,
    y: event.clientY - node.y
  }

  const onMouseMove = (e: MouseEvent) => {
    if (isDragging.value) {
      node.x = e.clientX - dragOffset.value.x
      node.y = e.clientY - dragOffset.value.y
    }
  }

  const onMouseUp = () => {
    isDragging.value = false
    window.removeEventListener('mousemove', onMouseMove)
    window.removeEventListener('mouseup', onMouseUp)
  }

  window.addEventListener('mousemove', onMouseMove)
  window.addEventListener('mouseup', onMouseUp)
}

function addNode() {
  const newNode: PathwayNode = {
    id: `node-${Date.now()}`,
    type: 'task',
    label: '新节点',
    x: 100,
    y: 100
  }
  emit('update:nodes', [...props.nodes, newNode])
}

function deleteNode() {
  if (!selectedNode.value) return
  emit('update:nodes', props.nodes.filter(n => n.id !== selectedNode.value!.id))
  emit('update:edges', props.edges.filter(e => e.source !== selectedNode.value!.id && e.target !== selectedNode.value!.id))
  selectedNode.value = null
}

function addEdge() {
  if (!selectedNode.value) return
  const target = prompt('输入目标节点 ID:')
  if (!target) return

  const newEdge: PathwayEdge = {
    id: `edge-${Date.now()}`,
    source: selectedNode.value.id,
    target
  }
  emit('update:edges', [...props.edges, newEdge])
}

function savePathway() {
  emit('save')
}

onMounted(() => {
  if (canvas.value) {
    canvasWidth.value = canvas.value.clientWidth
    canvasHeight.value = canvas.value.clientHeight
  }
})
</script>

<style scoped>
.clinical-pathway {
  display: flex;
  flex-direction: column;
  gap: 16px;
  background: #fff;
  border-radius: 8px;
  border: 1px solid var(--color-border, #E3E7EC);
  padding: 16px;
}

.pathway-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.pathway-title {
  font-size: 16px;
  font-weight: 600;
  margin: 0;
}

.pathway-controls {
  display: flex;
  gap: 8px;
}

.pathway-container {
  display: flex;
  gap: 16px;
}

.pathway-canvas {
  flex: 1;
  min-height: 400px;
  background: #f8f9fa;
  border-radius: 4px;
  overflow: hidden;
}

.pathway-canvas svg {
  width: 100%;
  height: 100%;
}

.node {
  cursor: pointer;
}

.node:hover rect {
  filter: brightness(1.1);
}

.node-editor {
  width: 280px;
  padding: 16px;
  background: #f8f9fa;
  border-radius: 4px;
}

.node-editor h4 {
  margin: 0 0 12px;
  font-size: 14px;
  font-weight: 600;
}

.form-group {
  margin-bottom: 12px;
}

.form-group label {
  display: block;
  margin-bottom: 4px;
  font-size: 12px;
  font-weight: 500;
  color: #666;
}

.form-input,
.form-select,
.form-textarea {
  width: 100%;
  padding: 8px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 13px;
}

.form-textarea {
  font-family: monospace;
}

.editor-actions {
  display: flex;
  gap: 8px;
  margin-top: 12px;
}
</style>
