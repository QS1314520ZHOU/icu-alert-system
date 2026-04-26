<template>
  <div class="organ-radar" :style="{ '--radar-size': `${size}px` }">
    <svg :viewBox="`0 0 ${viewSize} ${viewSize}`" class="organ-radar__svg" aria-hidden="true">
      <polygon
        v-for="(ring, index) in gridPolygons"
        :key="`ring-${index}`"
        :points="ring"
        class="organ-radar__ring"
      />
      <line
        v-for="axis in axisLines"
        :key="axis.key"
        :x1="center"
        :y1="center"
        :x2="axis.x"
        :y2="axis.y"
        class="organ-radar__axis"
      />
      <polygon :points="valuePolygon" class="organ-radar__value-fill" />
      <polyline :points="valuePolygon" class="organ-radar__value-line" />
      <circle
        v-for="point in valuePoints"
        :key="point.key"
        :cx="point.x"
        :cy="point.y"
        r="3.5"
        class="organ-radar__value-dot"
      />
      <text
        v-for="label in labelPoints"
        :key="label.key"
        :x="label.x"
        :y="label.y"
        class="organ-radar__label"
        text-anchor="middle"
      >
        {{ label.label }}
      </text>
    </svg>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { BODY_MAP_ORGAN_LABELS, BODY_MAP_ORGAN_ORDER } from '../../utils/bodyMap'

const props = withDefaults(defineProps<{
  scores?: number[]
  labels?: string[]
  size?: number
  max?: number
}>(), {
  scores: () => [],
  labels: () => [],
  size: 126,
  max: 3,
})

const viewSize = 160
const center = viewSize / 2
const radius = 48
const axisCount = BODY_MAP_ORGAN_ORDER.length

function polarPoint(index: number, scale: number, offset = 0) {
  const angle = ((Math.PI * 2) / axisCount) * index - Math.PI / 2
  const r = radius * scale
  return {
    x: center + Math.cos(angle) * (r + offset),
    y: center + Math.sin(angle) * (r + offset),
  }
}

const safeScores = computed(() =>
  BODY_MAP_ORGAN_ORDER.map((_, index) => {
    const value = Number(props.scores?.[index] ?? 0)
    if (!Number.isFinite(value)) return 0
    return Math.max(0, Math.min(props.max, value))
  })
)

const displayLabels = computed(() =>
  BODY_MAP_ORGAN_ORDER.map((key, index) => props.labels?.[index] || BODY_MAP_ORGAN_LABELS[key])
)

const gridPolygons = computed(() =>
  [0.33, 0.66, 1].map((scale) =>
    BODY_MAP_ORGAN_ORDER.map((_, index) => {
      const point = polarPoint(index, scale)
      return `${point.x},${point.y}`
    }).join(' ')
  )
)

const axisLines = computed(() =>
  BODY_MAP_ORGAN_ORDER.map((key, index) => ({
    key,
    ...polarPoint(index, 1),
  }))
)

const valuePoints = computed(() =>
  BODY_MAP_ORGAN_ORDER.map((key, index) => {
    const point = polarPoint(index, (safeScores.value[index] ?? 0) / props.max)
    return { key, ...point }
  })
)

const valuePolygon = computed(() =>
  valuePoints.value.map((point) => `${point.x},${point.y}`).join(' ')
)

const labelPoints = computed(() =>
  BODY_MAP_ORGAN_ORDER.map((key, index) => ({
    key,
    label: displayLabels.value[index],
    ...polarPoint(index, 1, 18),
  }))
)
</script>

<style scoped>
.organ-radar {
  width: var(--radar-size);
  height: var(--radar-size);
}
.organ-radar__svg {
  width: 100%;
  height: 100%;
  display: block;
}
.organ-radar__ring {
  fill: rgba(18, 43, 67, 0.36);
  stroke: rgba(91, 164, 201, 0.18);
  stroke-width: 1;
}
.organ-radar__axis {
  stroke: rgba(95, 167, 205, 0.18);
  stroke-width: 1;
}
.organ-radar__value-fill {
  fill: rgba(56, 189, 248, 0.22);
}
.organ-radar__value-line {
  fill: none;
  stroke: #38bdf8;
  stroke-width: 2;
}
.organ-radar__value-dot {
  fill: #7dd3fc;
}
.organ-radar__label {
  fill: #8fb8ca;
  font-size: 10px;
  dominant-baseline: middle;
}
html[data-theme='light'] .organ-radar__ring {
  fill: rgba(225, 239, 247, 0.7);
  stroke: rgba(123, 164, 189, 0.26);
}
html[data-theme='light'] .organ-radar__axis {
  stroke: rgba(123, 164, 189, 0.24);
}
html[data-theme='light'] .organ-radar__label {
  fill: #56748d;
}
</style>
