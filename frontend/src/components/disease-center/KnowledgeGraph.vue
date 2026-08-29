<template>
  <div class="knowledge-graph">
    <div class="graph-header">
      <h3 class="graph-title">病种知识图谱</h3>
      <div class="graph-controls">
        <button class="btn btn--sm btn--outline" @click="zoomIn">放大</button>
        <button class="btn btn--sm btn--outline" @click="zoomOut">缩小</button>
        <button class="btn btn--sm btn--outline" @click="resetView">重置</button>
      </div>
    </div>
    <div class="graph-container" ref="graphContainer">
      <svg :width="width" :height="height">
        <!-- 边 -->
        <g class="edges">
          <line
            v-for="edge in edges"
            :key="edge.id"
            :x1="edge.source.x"
            :y1="edge.source.y"
            :x2="edge.target.x"
            :y2="edge.target.y"
            :stroke="edge.color || '#999'"
            :stroke-width="edge.width || 1"
            :stroke-dasharray="edge.dashed ? '5,5' : ''"
          />
          <text
            v-for="edge in edges"
            :key="edge.id + '-label'"
            :x="(edge.source.x + edge.target.x) / 2"
            :y="(edge.source.y + edge.target.y) / 2"
            class="edge-label"
            text-anchor="middle"
            dominant-baseline="middle"
          >
            {{ edge.label }}
          </text>
        </g>

        <!-- 节点 -->
        <g class="nodes">
          <g
            v-for="node in nodes"
            :key="node.id"
            :transform="`translate(${node.x}, ${node.y})`"
            class="node"
            @click="selectNode(node)"
          >
            <circle
              :r="node.radius || 20"
              :fill="node.color || '#4C80F1'"
              :stroke="selectedNode?.id === node.id ? '#333' : 'transparent'"
              stroke-width="2"
            />
            <text
              class="node-label"
              text-anchor="middle"
              dominant-baseline="middle"
              :fill="node.textColor || '#fff'"
            >
              {{ node.label }}
            </text>
          </g>
        </g>
      </svg>
    </div>

    <!-- 节点详情 -->
    <div v-if="selectedNode" class="node-detail">
      <h4>{{ selectedNode.label }}</h4>
      <p v-if="selectedNode.description">{{ selectedNode.description }}</p>
      <div v-if="selectedNode.metadata" class="node-metadata">
        <div v-for="(value, key) in selectedNode.metadata" :key="key" class="metadata-item">
          <span class="metadata-key">{{ key }}:</span>
          <span class="metadata-value">{{ value }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'

interface GraphNode {
  id: string
  label: string
  x: number
  y: number
  radius?: number
  color?: string
  textColor?: string
  description?: string
  metadata?: Record<string, any>
}

interface GraphEdge {
  id: string
  source: GraphNode
  target: GraphNode
  label?: string
  color?: string
  width?: number
  dashed?: boolean
}

const props = defineProps<{
  nodes: GraphNode[]
  edges: GraphEdge[]
}>()

const emit = defineEmits<{
  (e: 'node-click', node: GraphNode): void
}>()

const graphContainer = ref<HTMLElement | null>(null)
const width = ref(800)
const height = ref(600)
const selectedNode = ref<GraphNode | null>(null)

function selectNode(node: GraphNode) {
  selectedNode.value = node
  emit('node-click', node)
}

function zoomIn() {
  // TODO: 实现缩放
}

function zoomOut() {
  // TODO: 实现缩放
}

function resetView() {
  selectedNode.value = null
  // TODO: 重置视图
}

onMounted(() => {
  if (graphContainer.value) {
    width.value = graphContainer.value.clientWidth
    height.value = graphContainer.value.clientHeight
  }
})
</script>

<style scoped>
.knowledge-graph {
  display: flex;
  flex-direction: column;
  gap: 16px;
  background: #fff;
  border-radius: 8px;
  border: 1px solid var(--color-border, #E3E7EC);
  padding: 16px;
}

.graph-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.graph-title {
  font-size: 16px;
  font-weight: 600;
  margin: 0;
}

.graph-controls {
  display: flex;
  gap: 8px;
}

.graph-container {
  flex: 1;
  min-height: 400px;
  background: #f8f9fa;
  border-radius: 4px;
  overflow: hidden;
}

.graph-container svg {
  width: 100%;
  height: 100%;
}

.node {
  cursor: pointer;
}

.node:hover circle {
  filter: brightness(1.1);
}

.node-label {
  font-size: 12px;
  font-weight: 500;
  pointer-events: none;
}

.edge-label {
  font-size: 10px;
  fill: #666;
  pointer-events: none;
}

.node-detail {
  padding: 12px;
  background: #f8f9fa;
  border-radius: 4px;
}

.node-detail h4 {
  margin: 0 0 8px;
  font-size: 14px;
  font-weight: 600;
}

.node-detail p {
  margin: 0 0 8px;
  font-size: 13px;
  color: #666;
}

.node-metadata {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.metadata-item {
  display: flex;
  gap: 8px;
  font-size: 12px;
}

.metadata-key {
  font-weight: 500;
  color: #333;
}

.metadata-value {
  color: #666;
}
</style>
