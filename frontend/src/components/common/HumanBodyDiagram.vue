<template>
  <div :class="['human-body', { 'human-body--compact': compact }]">
    <div class="human-body__frame">
      <svg viewBox="0 0 260 580" class="human-body__svg" aria-hidden="true">
        <defs>
          <linearGradient :id="svgDefId('body-shell-fill')" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="#28607b" stop-opacity="0.22" />
            <stop offset="55%" stop-color="#0f273a" stop-opacity="0.84" />
            <stop offset="100%" stop-color="#06121f" stop-opacity="0.96" />
          </linearGradient>
          <linearGradient :id="svgDefId('body-core-fill')" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="#91e4ff" stop-opacity="0.1" />
            <stop offset="100%" stop-color="#1e5574" stop-opacity="0.02" />
          </linearGradient>

          <radialGradient :id="svgDefId('heat-gradient-normal')" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stop-color="#d9fff5" stop-opacity="0.95" />
            <stop offset="30%" stop-color="#1A9C5B" stop-opacity="0.7" />
            <stop offset="100%" stop-color="#1A9C5B" stop-opacity="0" />
          </radialGradient>
          <radialGradient :id="svgDefId('heat-gradient-warning')" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stop-color="#fff8cc" stop-opacity="0.95" />
            <stop offset="30%" stop-color="#FFF7E8" stop-opacity="0.75" />
            <stop offset="100%" stop-color="#E8901C" stop-opacity="0" />
          </radialGradient>
          <radialGradient :id="svgDefId('heat-gradient-high')" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stop-color="#fff0dc" stop-opacity="0.95" />
            <stop offset="30%" stop-color="#A65A0C" stop-opacity="0.78" />
            <stop offset="100%" stop-color="#E8901C" stop-opacity="0" />
          </radialGradient>
          <radialGradient :id="svgDefId('heat-gradient-critical')" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stop-color="#ffe0e7" stop-opacity="1" />
            <stop offset="30%" stop-color="#D9342B" stop-opacity="0.82" />
            <stop offset="100%" stop-color="#D9342B" stop-opacity="0" />
          </radialGradient>

          <filter :id="svgDefId('body-outer-glow')" x="-30%" y="-10%" width="160%" height="140%">
            <feGaussianBlur stdDeviation="10" result="blur" />
            <feColorMatrix
              in="blur"
              type="matrix"
              values="1 0 0 0 0.05  0 1 0 0 0.66  0 0 1 0 0.92  0 0 0 0.35 0"
            />
          </filter>
          <filter :id="svgDefId('body-heat-blur')" x="-60%" y="-60%" width="220%" height="220%">
            <feGaussianBlur stdDeviation="12" />
          </filter>
          <filter :id="svgDefId('body-organ-glow')" x="-30%" y="-30%" width="160%" height="160%">
            <feGaussianBlur stdDeviation="3.8" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
          <clipPath :id="svgDefId('body-silhouette-clip')">
            <path :d="bodySilhouettePath" :transform="silhouetteTransform" />
          </clipPath>
        </defs>

        <g class="human-body__scene">
          <path :d="bodySilhouettePath" class="human-body__halo" :filter="svgUrl('body-outer-glow')" :transform="silhouetteTransform" />
          <path :d="bodySilhouettePath" class="human-body__silhouette" :fill="svgUrl('body-shell-fill')" :transform="silhouetteTransform" />
          <path :d="bodyCorePath" class="human-body__core" :fill="svgUrl('body-core-fill')" :transform="silhouetteTransform" />

          <g class="human-body__hud" :clip-path="svgUrl('body-silhouette-clip')">
            <path v-for="(line, index) in hudLines" :key="`hud-${index}`" :d="line" class="human-body__hud-line" />
            <path v-for="(line, index) in bodyGuides" :key="`guide-${index}`" :d="line" class="human-body__guide-line" />

            <g
              v-for="region in renderedRegions"
              :key="region.key"
              :class="regionGroupClass(region.key, region.severity)"
              @mouseenter="handleRegionEnter(region.key)"
              @mouseleave="handleRegionLeave"
              @click="handleRegionClick(region.key)"
            >
              <ellipse
                v-for="(hotspot, index) in region.hotspots"
                :key="`${region.key}-hotspot-${index}`"
                class="human-body__heat"
                :cx="hotspot.cx"
                :cy="hotspot.cy"
                :rx="hotspot.rx"
                :ry="hotspot.ry"
                :fill="svgUrl(`heat-gradient-${region.severity}`)"
                :filter="svgUrl('body-heat-blur')"
              />
              <ellipse
                v-for="(hotspot, index) in region.hotspots"
                :key="`${region.key}-core-${index}`"
                class="human-body__heat-core"
                :cx="hotspot.cx"
                :cy="hotspot.cy"
                :rx="hotspot.rx * (hotspot.coreScale || 0.5)"
                :ry="hotspot.ry * (hotspot.coreScale || 0.5)"
                :style="heatCoreStyle(region.severity)"
              />
              <path
                v-for="(outline, index) in region.outlines"
                :key="`${region.key}-outline-${index}`"
                class="human-body__organ-outline"
                :class="outline.className"
                :d="outline.d"
                :style="outlineStyle(region.severity, outline)"
                :filter="svgUrl('body-organ-glow')"
              />
            </g>
          </g>

          <path :d="bodySilhouettePath" class="human-body__frame-line" :transform="silhouetteTransform" />

          <g v-if="compact && deviceConnectorPaths.length" class="human-body__device-links">
            <path
              v-for="line in deviceConnectorPaths"
              :key="line.key"
              :d="line.d"
              :class="['human-body__device-link', `is-${line.severity}`]"
            />
          </g>
        </g>
      </svg>

      <div
        v-if="hoveredOrgan && hoveredTooltip"
        class="human-body__tooltip"
        :style="badgeStyle(tooltipAnchor(hoveredOrgan))"
      >
        <div class="human-body__tooltip-head">
          <strong>{{ hoveredTooltip.label }}</strong>
          <span :class="['human-body__tooltip-sev', `is-${hoveredTooltip.severity}`]">{{ hoveredTooltip.statusText }}</span>
        </div>
        <div v-if="hoveredTooltip.detail" class="human-body__tooltip-body">{{ hoveredTooltip.detail }}</div>
      </div>

      <div v-for="badge in metricBadges" :key="badge.key" :class="['human-body__badge', `is-${badge.tone || 'normal'}`]" :style="badgeStyle(badge.anchor)">
        <div class="human-body__badge-top">
          <span>{{ badge.label }}</span>
          <strong>{{ badge.value }}</strong>
        </div>
        <div v-if="badge.meta || badge.trendText" class="human-body__badge-foot">
          <span>{{ badge.meta }}</span>
          <span v-if="badge.trendText" :class="['human-body__trend', `is-${badge.trendTone || 'stable'}`]">{{ badge.trendText }}</span>
        </div>
      </div>

      <div
        v-for="marker in displayDeviceMarkers"
        :key="marker.key"
        :class="['human-body__device', `is-${marker.severity}`, { 'is-blink': marker.blink }]"
        :style="pointStyle(marker.targetX, marker.targetY)"
      >
        <span class="human-body__device-dot" />
        <div class="human-body__device-copy">
          <strong>{{ marker.label }}</strong>
          <span>{{ marker.daysText || marker.detail || '在位' }}</span>
        </div>
      </div>
    </div>

    <div v-if="showLegend" class="human-body__legend">
      <span v-for="item in legendItems" :key="item.key" class="human-body__legend-item">
        <i :class="['human-body__legend-dot', `is-${item.key}`]" />
        {{ item.label }}
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  BODY_MAP_ORGAN_LABELS,
  BODY_MAP_ORGAN_ORDER,
  normalizeBodyMapSeverity,
  type BodyMapSeverity,
} from '../../utils/bodyMap'

type AnchorKey = string

type OrganHotspot = {
  cx: number
  cy: number
  rx: number
  ry: number
  coreScale?: number
}

type OrganOutline = {
  d: string
  fillOpacity?: number
  strokeOpacity?: number
  strokeWidth?: number
  fillMode?: 'solid' | 'none'
  strokeLinecap?: 'butt' | 'round' | 'square'
  strokeLinejoin?: 'miter' | 'round' | 'bevel'
  className?: string
}

const props = withDefaults(defineProps<{
  organStates?: Record<string, any>
  selectedOrgan?: string
  compact?: boolean
  showLegend?: boolean
  metricBadges?: Array<{
    key: string
    label: string
    value: string
    meta?: string
    anchor: AnchorKey
    tone?: string
    trendText?: string
    trendTone?: string
  }>
  deviceMarkers?: Array<{
    key: string
    label: string
    site: AnchorKey
    severity: string
    daysText?: string
    detail?: string
    blink?: boolean
  }>
  organTooltips?: Record<string, { label?: string; detail?: string; statusText?: string; severity?: string }>
}>(), {
  organStates: () => ({}),
  selectedOrgan: '',
  compact: false,
  showLegend: false,
  metricBadges: () => [],
  deviceMarkers: () => [],
  organTooltips: () => ({}),
})

const emit = defineEmits<{
  (e: 'organ-click', key: string): void
}>()

const svgUid = `human-body-${Math.random().toString(36).slice(2, 9)}`

const silhouetteTransform = 'matrix(2.68 0 0 2.68 -146 12)'

const bodySilhouettePath = `
  M104.265,117.959c-0.304,3.58,2.126,22.529,3.38,29.959c0.597,3.52,2.234,9.255,1.645,12.3
  c-0.841,4.244-1.084,9.736-0.621,12.934c0.292,1.942,1.211,10.899-0.104,14.175
  c-0.688,1.718-1.949,10.522-1.949,10.522c-3.285,8.294-1.431,7.886-1.431,7.886
  c1.017,1.248,2.759,0.098,2.759,0.098c1.327,0.846,2.246-0.201,2.246-0.201
  c1.139,0.943,2.467-0.116,2.467-0.116c1.431,0.743,2.758-0.627,2.758-0.627
  c0.822,0.414,1.023-0.109,1.023-0.109c2.466-0.158-1.376-8.05-1.376-8.05
  c-0.92-7.088,0.913-11.033,0.913-11.033c6.004-17.805,6.309-22.53,3.909-29.24
  c-0.676-1.937-0.847-2.704-0.536-3.545c0.719-1.941,0.195-9.748,1.072-12.848
  c1.692-5.979,3.361-21.142,4.231-28.217c1.169-9.53-4.141-22.308-4.141-22.308
  c-1.163-5.2,0.542-23.727,0.542-23.727c2.381,3.705,2.29,10.245,2.29,10.245
  c-0.378,6.859,5.541,17.342,5.541,17.342c2.844,4.332,3.921,8.442,3.921,8.747
  c0,1.248-0.273,4.269-0.273,4.269l0.109,2.631c0.049,0.67,0.426,2.977,0.365,4.092
  c-0.444,6.862,0.646,5.571,0.646,5.571c0.92,0,1.931-5.522,1.931-5.522
  c0,1.424-0.348,5.687,0.42,7.295c0.919,1.918,1.595-0.329,1.607-0.78
  c0.243-8.737,0.768-6.448,0.768-6.448c0.511,7.088,1.139,8.689,2.265,8.135
  c0.853-0.407,0.073-8.506,0.073-8.506c1.461,4.811,2.569,5.577,2.569,5.577
  c2.411,1.693,0.92-2.983,0.585-3.909c-1.784-4.92-1.839-6.625-1.839-6.625
  c2.229,4.421,3.909,4.257,3.909,4.257c2.174-0.694-1.9-6.954-4.287-9.953
  c-1.218-1.528-2.789-3.574-3.245-4.789c-0.743-2.058-1.304-8.674-1.304-8.674
  c-0.225-7.807-2.155-11.198-2.155-11.198c-3.3-5.282-3.921-15.135-3.921-15.135
  l-0.146-16.635c-1.157-11.347-9.518-11.429-9.518-11.429c-8.451-1.258-9.627-3.988-9.627-3.988
  c-1.79-2.576-0.767-7.514-0.767-7.514c1.485-1.208,2.058-4.415,2.058-4.415
  c2.466-1.891,2.345-4.658,1.206-4.628c-0.914,0.024-0.707-0.733-0.707-0.733
  C115.068,0.636,104.01,0,104.01,0h-1.688c0,0-11.063,0.636-9.523,13.089
  c0,0,0.207,0.758-0.715,0.733c-1.136-0.03-1.242,2.737,1.215,4.628
  c0,0,0.572,3.206,2.058,4.415c0,0,1.023,4.938-0.767,7.514c0,0-1.172,2.73-9.627,3.988
  c0,0-8.375,0.082-9.514,11.429l-0.158,16.635c0,0-0.609,9.853-3.922,15.135
  c0,0-1.921,3.392-2.143,11.198c0,0-0.563,6.616-1.303,8.674
  c-0.451,1.209-2.021,3.255-3.249,4.789c-2.408,2.993-6.455,9.24-4.29,9.953
  c0,0,1.689,0.164,3.909-4.257c0,0-0.046,1.693-1.827,6.625c-0.35,0.914-1.839,5.59,0.573,3.909
  c0,0,1.117-0.767,2.569-5.577c0,0-0.779,8.099,0.088,8.506c1.133,0.555,1.751-1.047,2.262-8.135
  c0,0,0.524-2.289,0.767,6.448c0.012,0.451,0.673,2.698,1.596,0.78
  c0.779-1.608,0.429-5.864,0.429-7.295c0,0,0.999,5.522,1.933,5.522
  c0,0,1.099,1.291,0.648-5.571c-0.073-1.121,0.32-3.422,0.369-4.092l0.106-2.631
  c0,0-0.274-3.014-0.274-4.269c0-0.311,1.078-4.415,3.921-8.747
  c0,0,5.913-10.488,5.532-17.342c0,0-0.082-6.54,2.299-10.245
  c0,0,1.69,18.526,0.545,23.727c0,0-5.319,12.778-4.146,22.308
  c0.864,7.094,2.53,22.237,4.226,28.217c0.886,3.094,0.362,10.899,1.072,12.848
  c0.32,0.847,0.152,1.627-0.536,3.545c-2.387,6.71-2.083,11.436,3.921,29.24
  c0,0,1.848,3.945,0.914,11.033c0,0-3.836,7.892-1.379,8.05c0,0,0.192,0.523,1.023,0.109
  c0,0,1.327,1.37,2.761,0.627c0,0,1.328,1.06,2.463,0.116c0,0,0.91,1.047,2.237,0.201
  c0,0,1.742,1.175,2.777-0.098c0,0,1.839,0.408-1.435-7.886c0,0-1.254-8.793-1.945-10.522
  c-1.318-3.275-0.387-12.251-0.106-14.175c0.453-3.216,0.21-8.695-0.618-12.934
  c-0.606-3.038,1.035-8.774,1.641-12.3c1.245-7.423,3.685-26.373,3.38-29.959
  l1.008,0.354C103.809,118.312,104.265,117.959,104.265,117.959z
`

const bodyCorePath = `
  M103.2 25
  C95.5 28 90.5 33 86.4 38
  C82.7 42.6 81.3 52.4 82.2 65
  C83 76 87.4 87 86.5 96.6
  C84.8 114.2 84 128.5 87.8 143.5
  C91.8 159.5 94.4 172.7 93.2 190.5
  L99.1 190.5
  C101.6 166.5 101.9 144.3 102.3 120
  C102.6 144.3 103 166.5 106.8 190.5
  L113 190.5
  C111.7 172.7 114.3 159.5 118.4 143.5
  C122.1 128.5 121.3 114.2 119.6 96.6
  C118.7 87 123.1 76 123.9 65
  C124.8 52.4 123.4 42.6 119.7 38
  C115.8 33 110.8 28 103.2 25
  Z
`

const hudLines = [
  'M86 114 Q130 95 174 114',
  'M92 162 Q130 149 168 162',
  'M96 214 Q130 206 164 214',
  'M102 276 Q130 270 158 276',
  'M108 346 Q130 341 152 346',
  'M114 426 Q130 422 146 426',
]

const bodyGuides = [
  'M130 88 L130 528',
  'M100 132 Q130 144 160 132',
  'M105 236 Q130 246 155 236',
]

const regionShapes: Record<(typeof BODY_MAP_ORGAN_ORDER)[number], { hotspots: OrganHotspot[]; outlines: OrganOutline[] }> = {
  neurologic: {
    hotspots: [{ cx: 130, cy: 60, rx: 27, ry: 22, coreScale: 0.52 }],
    outlines: [
      { d: 'M112 54 C116 45 124 40 133 40 C142 40 149 46 150 56 C151 65 147 74 139 78 C136 79 133 80 130 82 C127 80 124 79 121 78 C113 74 109 65 112 54 Z', fillOpacity: 0.18, strokeWidth: 2.2 },
      { d: 'M130 44 C125 49 125 55 130 60 C135 55 135 49 130 44 M121 52 C118 58 119 64 123 69 M139 52 C142 58 141 64 137 69', fillMode: 'none', strokeOpacity: 0.72, strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' },
    ],
  },
  respiratory: {
    hotspots: [
      { cx: 109, cy: 169, rx: 30, ry: 50, coreScale: 0.46 },
      { cx: 151, cy: 169, rx: 30, ry: 50, coreScale: 0.46 },
    ],
    outlines: [
      { d: 'M120 124 C104 127 92 141 90 162 C88 184 94 205 105 219 C111 226 119 224 122 214 C125 202 125 188 124 174 L124 135 C123 128 122 125 120 124 Z', fillOpacity: 0.14, strokeWidth: 2.4, strokeLinejoin: 'round' },
      { d: 'M140 124 C156 127 168 141 170 162 C172 184 166 205 155 219 C149 226 141 224 138 214 C135 202 135 188 136 174 L136 135 C137 128 138 125 140 124 Z', fillOpacity: 0.14, strokeWidth: 2.4, strokeLinejoin: 'round' },
      { d: 'M130 118 L130 218', fillMode: 'none', strokeOpacity: 0.55, strokeWidth: 1.8, strokeLinecap: 'round' },
    ],
  },
  circulatory: {
    hotspots: [{ cx: 132, cy: 181, rx: 24, ry: 28, coreScale: 0.5 }],
    outlines: [
      { d: 'M132 151 C144 132 171 145 163 170 C158 184 145 193 132 205 C119 193 106 184 101 170 C93 145 120 132 132 151 Z', fillOpacity: 0.22, strokeWidth: 2.2, strokeLinejoin: 'round' },
      { d: 'M130 126 C130 136 130 144 132 151 M132 151 C141 143 147 136 149 126', fillMode: 'none', strokeOpacity: 0.7, strokeWidth: 1.7, strokeLinecap: 'round', strokeLinejoin: 'round' },
    ],
  },
  hepatic: {
    hotspots: [{ cx: 149, cy: 256, rx: 38, ry: 25, coreScale: 0.46 }],
    outlines: [
      { d: 'M123 232 C137 221 160 220 172 231 C177 236 179 244 177 252 C174 264 163 272 147 274 C132 276 119 271 113 262 C107 252 111 241 123 232 Z', fillOpacity: 0.16, strokeWidth: 2.2, strokeLinejoin: 'round' },
      { d: 'M126 238 C139 235 152 237 164 244', fillMode: 'none', strokeOpacity: 0.56, strokeWidth: 1.5, strokeLinecap: 'round' },
    ],
  },
  coagulation: {
    hotspots: [
      { cx: 130, cy: 150, rx: 20, ry: 28, coreScale: 0.45 },
      { cx: 130, cy: 220, rx: 18, ry: 34, coreScale: 0.44 },
      { cx: 130, cy: 304, rx: 20, ry: 48, coreScale: 0.42 },
    ],
    outlines: [
      { d: 'M130 119 C132 145 132 168 129 192 C126 216 125 242 128 268 C131 293 131 320 129 346', fillMode: 'none', strokeOpacity: 0.74, strokeWidth: 3.2, strokeLinecap: 'round', strokeLinejoin: 'round', className: 'is-vascular' },
      { d: 'M129 186 C118 197 113 211 111 228 M129 186 C141 198 147 212 149 228 M129 274 C118 288 112 304 109 324 M129 274 C140 288 146 304 149 324', fillMode: 'none', strokeOpacity: 0.66, strokeWidth: 2, strokeLinecap: 'round', strokeLinejoin: 'round', className: 'is-vascular' },
      { d: 'M129 148 C129 148 129 148 129 148', fillMode: 'none', strokeOpacity: 0.95, strokeWidth: 8, strokeLinecap: 'round', className: 'is-node' },
      { d: 'M129 224 C129 224 129 224 129 224', fillMode: 'none', strokeOpacity: 0.9, strokeWidth: 7, strokeLinecap: 'round', className: 'is-node' },
      { d: 'M129 304 C129 304 129 304 129 304', fillMode: 'none', strokeOpacity: 0.9, strokeWidth: 7, strokeLinecap: 'round', className: 'is-node' },
    ],
  },
  renal: {
    hotspots: [
      { cx: 107, cy: 284, rx: 18, ry: 28, coreScale: 0.48 },
      { cx: 153, cy: 284, rx: 18, ry: 28, coreScale: 0.48 },
    ],
    outlines: [
      { d: 'M108 250 C98 252 91 262 91 275 C91 288 97 300 107 304 C115 307 123 301 124 291 C126 280 124 267 119 258 C116 252 112 250 108 250 Z', fillOpacity: 0.16, strokeWidth: 2.2, strokeLinejoin: 'round' },
      { d: 'M152 250 C162 252 169 262 169 275 C169 288 163 300 153 304 C145 307 137 301 136 291 C134 280 136 267 141 258 C144 252 148 250 152 250 Z', fillOpacity: 0.16, strokeWidth: 2.2, strokeLinejoin: 'round' },
      { d: 'M124 291 C123 302 121 315 119 326 M136 291 C137 302 139 315 141 326', fillMode: 'none', strokeOpacity: 0.56, strokeWidth: 1.5, strokeLinecap: 'round' },
    ],
  },
}

const renderedRegions = computed(() =>
  BODY_MAP_ORGAN_ORDER.map((key) => ({
    key,
    label: BODY_MAP_ORGAN_LABELS[key],
    severity: normalizeBodyMapSeverity(props.organStates?.[key]),
    hotspots: regionShapes[key].hotspots,
    outlines: regionShapes[key].outlines,
  }))
)

const legendItems = [
  { key: 'normal', label: '正常' },
  { key: 'warning', label: '预警' },
  { key: 'high', label: '高危' },
  { key: 'critical', label: '危急' },
]

const anchorPositions: Record<AnchorKey, { left: string; top: string }> = {
  head: { left: '50%', top: '11%' },
  leftLung: { left: '34%', top: '31%' },
  rightLung: { left: '66%', top: '31%' },
  heart: { left: '56%', top: '34%' },
  abdomen: { left: '58%', top: '48%' },
  pelvis: { left: '50%', top: '61%' },
  leftArm: { left: '25%', top: '45%' },
  rightArm: { left: '75%', top: '45%' },
  mouth: { left: '50%', top: '12%' },
  neck: { left: '56%', top: '22%' },
  leftChest: { left: '34%', top: '33%' },
  rightChest: { left: '66%', top: '33%' },
}

const VIEWBOX_WIDTH = 260
const VIEWBOX_HEIGHT = 580

const organAnchors: Record<string, AnchorKey> = {
  neurologic: 'head',
  respiratory: 'rightChest',
  circulatory: 'leftChest',
  hepatic: 'abdomen',
  coagulation: 'heart',
  renal: 'pelvis',
}

const severityPalette: Record<BodyMapSeverity, { core: string; stroke: string; accent: string }> = {
  normal: { core: '#1A9C5B', stroke: '#E8FFEA', accent: '#1A9C5B' },
  warning: { core: '#E8901C', stroke: '#FFF7E8', accent: '#A65A0C' },
  high: { core: '#E8901C', stroke: '#FFF7E8', accent: '#A65A0C' },
  critical: { core: '#D9342B', stroke: '#FFECE8', accent: '#D9342B' },
}

const hoveredOrgan = ref('')

const hoveredTooltip = computed(() => {
  const key = hoveredOrgan.value
  if (!key) return null
  const severity = normalizeBodyMapSeverity(props.organStates?.[key])
  const payload = props.organTooltips?.[key] || {}
  return {
    label: payload.label || BODY_MAP_ORGAN_LABELS[key as keyof typeof BODY_MAP_ORGAN_LABELS] || key,
    detail: payload.detail || '',
    statusText: payload.statusText || severity,
    severity,
  }
})

function rgba(hex: string, alpha: number) {
  const cleaned = hex.replace('#', '')
  const value = cleaned.length === 3
    ? cleaned.split('').map((part) => part + part).join('')
    : cleaned
  const r = Number.parseInt(value.slice(0, 2), 16)
  const g = Number.parseInt(value.slice(2, 4), 16)
  const b = Number.parseInt(value.slice(4, 6), 16)
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}

function svgDefId(name: string) {
  return `${svgUid}-${name}`
}

function svgUrl(name: string) {
  return `url(#${svgDefId(name)})`
}

function paletteFor(severity: string) {
  return severityPalette[normalizeBodyMapSeverity(severity)]
}

function heatCoreStyle(severity: string) {
  const palette = paletteFor(severity)
  return {
    fill: rgba(palette.accent, 0.28),
    stroke: rgba(palette.stroke, 0.38),
    strokeWidth: '1.2px',
  }
}

function outlineStyle(severity: string, outline: OrganOutline) {
  const palette = paletteFor(severity)
  return {
    fill: outline.fillMode === 'none' ? 'none' : rgba(palette.core, outline.fillOpacity ?? 0.12),
    stroke: rgba(palette.stroke, outline.strokeOpacity ?? 0.84),
    strokeWidth: `${outline.strokeWidth ?? 2}px`,
    strokeLinecap: outline.strokeLinecap || 'round',
    strokeLinejoin: outline.strokeLinejoin || 'round',
  }
}

function parsePercent(value: string, fallback: number) {
  const n = Number.parseFloat(String(value || '').replace('%', ''))
  return Number.isFinite(n) ? n : fallback
}

function anchorPoint(anchor: AnchorKey) {
  const pos = anchorPositions[anchor] ?? anchorPositions.rightChest ?? { left: '50%', top: '33%' }
  const leftPct = parsePercent(pos.left, 50)
  const topPct = parsePercent(pos.top, 33)
  return {
    leftPct,
    topPct,
    x: (leftPct / 100) * VIEWBOX_WIDTH,
    y: (topPct / 100) * VIEWBOX_HEIGHT,
  }
}

function pointStyle(x: number, y: number) {
  return {
    left: `${((x / VIEWBOX_WIDTH) * 100).toFixed(2)}%`,
    top: `${((y / VIEWBOX_HEIGHT) * 100).toFixed(2)}%`,
  }
}

const displayDeviceMarkers = computed(() => {
  const base = (Array.isArray(props.deviceMarkers) ? props.deviceMarkers : []).map((marker) => {
    const source = anchorPoint(marker.site)
    return {
      ...marker,
      sourceX: source.x,
      sourceY: source.y,
      targetX: source.x,
      targetY: source.y,
    }
  })
  if (!props.compact || !base.length) return base

  const minGap = 18
  const sideOffset = 34
  const topPad = 16
  const bottomPad = VIEWBOX_HEIGHT - 16

  ;(['left', 'right'] as const).forEach((side) => {
    const group = base
      .filter((item) => (side === 'left' ? item.sourceX < VIEWBOX_WIDTH / 2 : item.sourceX >= VIEWBOX_WIDTH / 2))
      .sort((a, b) => a.sourceY - b.sourceY)

    let lastY = -999
    group.forEach((item) => {
      const nextY = Math.max(topPad, Math.min(bottomPad, item.sourceY))
      const targetY = nextY - lastY < minGap ? lastY + minGap : nextY
      item.targetY = Math.max(topPad, Math.min(bottomPad, targetY))
      item.targetX = side === 'left'
        ? Math.max(10, item.sourceX - sideOffset)
        : Math.min(VIEWBOX_WIDTH - 10, item.sourceX + sideOffset)
      lastY = item.targetY
    })
  })

  return base
})

const deviceConnectorPaths = computed(() =>
  displayDeviceMarkers.value
    .filter((item) => props.compact && (Math.abs(item.targetX - item.sourceX) > 0.5 || Math.abs(item.targetY - item.sourceY) > 0.5))
    .map((item) => {
      const midX = item.sourceX + (item.targetX - item.sourceX) * 0.5
      return {
        key: item.key,
        severity: item.severity || 'normal',
        d: `M ${item.sourceX.toFixed(2)} ${item.sourceY.toFixed(2)} C ${midX.toFixed(2)} ${item.sourceY.toFixed(2)}, ${midX.toFixed(2)} ${item.targetY.toFixed(2)}, ${item.targetX.toFixed(2)} ${item.targetY.toFixed(2)}`,
      }
    })
)

function badgeStyle(anchor: AnchorKey) {
  const point = anchorPoint(anchor)
  return pointStyle(point.x, point.y)
}

function tooltipAnchor(key: string) {
  return organAnchors[key] || 'rightChest'
}

function handleRegionClick(key: string) {
  emit('organ-click', key)
}

function handleRegionEnter(key: string) {
  hoveredOrgan.value = key
}

function handleRegionLeave() {
  hoveredOrgan.value = ''
}

function regionGroupClass(key: string, severity: string) {
  return [
    'human-body__region-group',
    `is-${severity}`,
    {
      'is-selected': props.selectedOrgan === key,
      'is-pulse': severity === 'high' || severity === 'critical',
    },
  ]
}
</script>

<style scoped>
.human-body {
  display: grid;
  gap: 10px;
}
.human-body__frame {
  position: relative;
  width: min(100%, 320px);
  margin: 0 auto;
}
.human-body--compact .human-body__frame {
  width: min(100%, 150px);
}
.human-body__svg {
  width: 100%;
  height: auto;
  display: block;
}
.human-body__scene {
  isolation: isolate;
}
.human-body__halo {
  fill: rgba(56, 189, 248, 0.14);
  opacity: 0.9;
}
.human-body__silhouette {
  stroke: rgba(133, 215, 246, 0.34);
  stroke-width: 1.8;
}
.human-body__core {
  stroke: rgba(103, 188, 224, 0.12);
  stroke-width: 1.2;
}
.human-body__hud-line,
.human-body__guide-line,
.human-body__frame-line {
  fill: none;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.human-body__hud-line {
  stroke: rgba(121, 209, 241, 0.11);
  stroke-width: 1;
}
.human-body__guide-line {
  stroke: rgba(121, 209, 241, 0.15);
  stroke-dasharray: 4 6;
  stroke-width: 1;
}
.human-body__frame-line {
  stroke: rgba(121, 209, 241, 0.24);
  stroke-width: 1.4;
}
.human-body__device-link {
  fill: none;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 1.35;
  opacity: 0.66;
  stroke: rgba(94, 200, 236, 0.62);
}
.human-body__device-link.is-warning { stroke: rgba(245, 158, 11, 0.58); }
.human-body__device-link.is-high { stroke: rgba(249, 115, 22, 0.62); }
.human-body__device-link.is-critical { stroke: rgba(244, 63, 94, 0.66); }
.human-body__region-group {
  cursor: pointer;
  transition: opacity .2s ease, transform .2s ease;
}
.human-body__region-group:hover {
  transform: scale(1.02);
  transform-origin: center;
}
.human-body__heat {
  mix-blend-mode: screen;
  opacity: 0.9;
}
.human-body__heat-core,
.human-body__organ-outline {
  transition: opacity .2s ease, stroke .2s ease, fill .2s ease, transform .2s ease;
}
.human-body__organ-outline {
  vector-effect: non-scaling-stroke;
}
.human-body__organ-outline.is-vascular {
  opacity: 0.86;
}
.human-body__organ-outline.is-node {
  opacity: 0.94;
}
.human-body__region-group.is-selected .human-body__organ-outline,
.human-body__region-group.is-selected .human-body__heat-core {
  opacity: 1;
}
.human-body__region-group.is-selected .human-body__organ-outline {
  transform: translateZ(0);
}
.human-body__region-group.is-selected .human-body__heat {
  opacity: 1;
}
.human-body__region-group.is-selected {
  filter: drop-shadow(0 0 10px rgba(110, 231, 249, 0.24));
}
.human-body__region-group.is-pulse .human-body__heat-core,
.human-body__region-group.is-pulse .human-body__heat {
  animation: body-region-pulse 1.8s ease-in-out infinite;
}
.human-body__tooltip {
  position: absolute;
  min-width: 120px;
  max-width: 156px;
  padding: 10px 12px;
  border-radius: var(--card-radius);
  background: var(--bg-surface), 0.96);
  border: 1px solid rgba(110,231,249,.22);
  box-shadow: var(--card-shadow);
  backdrop-filter: blur(10px);
  transform: translate(-50%, -50%);
  pointer-events: none;
  z-index: 2;
}
.human-body__tooltip-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.human-body__tooltip-head strong {
  color: var(--text-primary);
  font-size: 12px;
}
.human-body__tooltip-body {
  margin-top: 6px;
  color: var(--text-secondary);
  font-size: 11px;
  line-height: 1.55;
}
.human-body__tooltip-sev {
  display: inline-flex;
  align-items: center;
  min-height: 20px;
  padding: 0 8px;
  border-radius: var(--card-radius);
  background: var(--bg-surface), 0.9);
  border: 1px solid rgba(84, 181, 222, 0.18);
  color: var(--text-primary);
  font-size: 10px;
}
.human-body__tooltip-sev.is-warning { color: var(--warning-soft); border-color: rgba(245,158,11,.22); }
.human-body__tooltip-sev.is-high { color: var(--warning-soft); border-color: rgba(249,115,22,.24); }
.human-body__tooltip-sev.is-critical { color: var(--danger-soft); border-color: rgba(244,63,94,.24); }
.human-body__badge,
.human-body__device {
  position: absolute;
  transform: translate(-50%, -50%);
}
.human-body__badge {
  min-width: 104px;
  max-width: 128px;
  padding: 8px 10px;
  border-radius: var(--card-radius);
  background: var(--bg-surface), 0.9);
  border: 1px solid rgba(104, 193, 229, 0.22);
  box-shadow: var(--card-shadow);
  backdrop-filter: blur(10px);
}
.human-body__badge-top,
.human-body__badge-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.human-body__badge-top span,
.human-body__badge-foot span {
  color: var(--text-secondary);
  font-size: 11px;
}
.human-body__badge-top strong {
  color: var(--text-primary);
  font-size: 14px;
}
.human-body__badge.is-warning { border-color: rgba(245, 158, 11, 0.32); }
.human-body__badge.is-high { border-color: rgba(249, 115, 22, 0.38); }
.human-body__badge.is-critical { border-color: rgba(244, 63, 94, 0.4); }
.human-body__trend {
  font-weight: 700;
}
.human-body__trend.is-up { color: var(--danger); }
.human-body__trend.is-down { color: var(--chart-1); }
.human-body__trend.is-stable { color: var(--chart-2); }
.human-body__device {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 76px;
  max-width: 118px;
  padding: 6px 8px;
  border-radius: var(--card-radius);
  background: var(--bg-surface), 0.96);
  border: 1px solid rgba(84, 181, 222, 0.18);
  backdrop-filter: blur(10px);
}
.human-body__device.is-warning { border-color: rgba(245, 158, 11, 0.34); }
.human-body__device.is-high { border-color: rgba(249, 115, 22, 0.36); }
.human-body__device.is-critical { border-color: rgba(244, 63, 94, 0.42); box-shadow: var(--card-shadow); }
.human-body__device.is-blink {
  animation: body-device-blink 1.15s ease-in-out infinite;
}
.human-body__device-dot {
  width: 10px;
  height: 10px;
  border-radius: var(--card-radius);
  background: currentColor;
  color: var(--chart-1);
  box-shadow: var(--card-shadow);
}
.human-body__device.is-warning .human-body__device-dot { color: var(--warning); }
.human-body__device.is-high .human-body__device-dot { color: var(--warning); }
.human-body__device.is-critical .human-body__device-dot { color: var(--danger-strong); }
.human-body__device-copy {
  display: grid;
  gap: 2px;
  min-width: 0;
}
.human-body__device-copy strong {
  color: var(--text-primary);
  font-size: 11px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.human-body__device-copy span {
  color: var(--text-secondary);
  font-size: 10px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.human-body--compact .human-body__device {
  min-width: 0;
  max-width: none;
  padding: 2px;
  border-radius: var(--card-radius);
  background: var(--bg-surface), 0.68);
  border: 1px solid rgba(104, 193, 229, 0.26);
  box-shadow: var(--card-shadow);
  backdrop-filter: none;
}

.human-body--compact .human-body__device-copy {
  display: none;
}

.human-body--compact .human-body__device-dot {
  width: 9px;
  height: 9px;
}

.human-body--compact .human-body__tooltip {
  display: none;
}
.human-body__legend {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 10px;
}
.human-body__legend-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--text-secondary);
  font-size: 12px;
}
.human-body__legend-dot {
  width: 10px;
  height: 10px;
  border-radius: var(--card-radius);
  display: inline-block;
  box-shadow: var(--card-shadow);
}
.human-body__legend-dot.is-normal { background: var(--chart-2); color: var(--chart-2); }
.human-body__legend-dot.is-warning { background: var(--warning); color: var(--warning); }
.human-body__legend-dot.is-high { background: var(--warning); color: #E8901C; }
.human-body__legend-dot.is-critical { background: var(--danger-strong); color: var(--danger-strong); }
@keyframes body-device-blink {
  0%, 100% { box-shadow: var(--card-shadow); }
  50% { box-shadow: var(--card-shadow); }
}
@keyframes body-region-pulse {
  0%, 100% { opacity: .78; }
  50% { opacity: 1; }
}
html[data-theme='light'] .human-body__halo {
  fill: rgba(48, 169, 222, 0.1);
}
html[data-theme='light'] .human-body__silhouette {
  fill: rgba(232, 244, 250, 0.96);
  stroke: rgba(124, 160, 183, 0.3);
}
html[data-theme='light'] .human-body__core {
  fill: rgba(193, 223, 239, 0.22);
  stroke: rgba(141, 180, 205, 0.18);
}
html[data-theme='light'] .human-body__hud-line,
html[data-theme='light'] .human-body__guide-line,
html[data-theme='light'] .human-body__frame-line {
  stroke: rgba(95, 145, 174, 0.2);
}
html[data-theme='light'] .human-body__device-link {
  stroke: rgba(84, 138, 171, 0.58);
}
html[data-theme='light'] .human-body__device-link.is-warning { stroke: rgba(217, 119, 6, 0.56); }
html[data-theme='light'] .human-body__device-link.is-high { stroke: rgba(234, 88, 12, 0.58); }
html[data-theme='light'] .human-body__device-link.is-critical { stroke: rgba(225, 29, 72, 0.62); }
html[data-theme='light'] .human-body__badge,
html[data-theme='light'] .human-body__device {
  background: rgba(255, 255, 255, 0.92);
  border-color: rgba(118, 164, 193, 0.24);
}
html[data-theme='light'] .human-body--compact .human-body__device {
  background: rgba(255, 255, 255, 0.86);
  border-color: rgba(118, 164, 193, 0.34);
}
html[data-theme='light'] .human-body__tooltip {
  background: rgba(255,255,255,.96);
  border-color: rgba(130,170,194,.24);
}
html[data-theme='light'] .human-body__badge-top strong,
html[data-theme='light'] .human-body__tooltip-head strong,
html[data-theme='light'] .human-body__device-copy strong {
  color: var(--text-secondary);
}
html[data-theme='light'] .human-body__badge-top span,
html[data-theme='light'] .human-body__badge-foot span,
html[data-theme='light'] .human-body__device-copy span,
html[data-theme='light'] .human-body__legend-item,
html[data-theme='light'] .human-body__tooltip-body {
  color: var(--text-secondary);
}
</style>
