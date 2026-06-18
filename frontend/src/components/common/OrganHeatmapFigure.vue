<template>
  <div :class="['organ-heatmap', { 'organ-heatmap--compact': compact }]">
    <div class="organ-heatmap__frame">
      <svg
        viewBox="0 0 400 700"
        class="organ-heatmap__svg"
        role="img"
        aria-label="人体器官热力图"
      >
        <defs>
          <radialGradient :id="svgDefId('bg-fill')" cx="50%" cy="22%" r="80%">
            <stop class="organ-heatmap__svg-stop organ-heatmap__svg-stop--bg-0" offset="0%" stop-color="#12213a" />
            <stop class="organ-heatmap__svg-stop organ-heatmap__svg-stop--bg-58" offset="58%" stop-color="#0a1628" />
            <stop class="organ-heatmap__svg-stop organ-heatmap__svg-stop--bg-100" offset="100%" stop-color="#08111f" />
          </radialGradient>

          <linearGradient :id="svgDefId('body-fill')" x1="0" y1="0" x2="0" y2="1">
            <stop class="organ-heatmap__svg-stop organ-heatmap__svg-stop--body-0" offset="0%" stop-color="#93f7ff" stop-opacity="0.30" />
            <stop class="organ-heatmap__svg-stop organ-heatmap__svg-stop--body-45" offset="45%" stop-color="#74e4ef" stop-opacity="0.22" />
            <stop class="organ-heatmap__svg-stop organ-heatmap__svg-stop--body-100" offset="100%" stop-color="#4ab8ca" stop-opacity="0.14" />
          </linearGradient>

          <linearGradient :id="svgDefId('body-core')" x1="0" y1="0" x2="0" y2="1">
            <stop class="organ-heatmap__svg-stop organ-heatmap__svg-stop--core-0" offset="0%" stop-color="#d8feff" stop-opacity="0.11" />
            <stop class="organ-heatmap__svg-stop organ-heatmap__svg-stop--core-100" offset="100%" stop-color="#8aefff" stop-opacity="0.02" />
          </linearGradient>

          <filter :id="svgDefId('body-glow')" x="-26%" y="-10%" width="152%" height="130%">
            <feGaussianBlur stdDeviation="8" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>

          <filter :id="svgDefId('organ-glow')" x="-35%" y="-35%" width="170%" height="170%">
            <feGaussianBlur stdDeviation="5" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        <rect width="400" height="700" :fill="svgUrl('bg-fill')" />

        <g class="organ-heatmap__figure" :transform="figureTransform">
          <path :d="activeLeftArmPath" class="organ-heatmap__body organ-heatmap__body--glow" :filter="svgUrl('body-glow')" :transform="silhouetteTransform" />
          <path :d="activeRightArmPath" class="organ-heatmap__body organ-heatmap__body--glow" :filter="svgUrl('body-glow')" :transform="silhouetteTransform" />
          <path :d="activeBodyPath" class="organ-heatmap__body organ-heatmap__body--glow" :filter="svgUrl('body-glow')" :transform="silhouetteTransform" />

          <path :d="activeLeftArmPath" class="organ-heatmap__body" :fill="svgUrl('body-fill')" :transform="silhouetteTransform" />
          <path :d="activeRightArmPath" class="organ-heatmap__body" :fill="svgUrl('body-fill')" :transform="silhouetteTransform" />
          <path :d="activeBodyPath" class="organ-heatmap__body" :fill="svgUrl('body-fill')" :transform="silhouetteTransform" />
          <path :d="activeBodyCorePath" class="organ-heatmap__core" :fill="svgUrl('body-core')" :transform="silhouetteTransform" />

          <g class="organ-heatmap__organs" :transform="organLayerTransform">
            <g
              v-for="organ in renderedOrgans"
              :key="organ.key"
              :class="organGroupClass(organ.key, organ.severity)"
              :filter="svgUrl('organ-glow')"
              @click="handleOrganClick(organ.key)"
            >
              <title>{{ organTitle(organ.key, organ.severity) }}</title>
              <path
                v-for="(segment, index) in organ.segments"
                :key="`${organ.key}-${index}`"
                :d="segment.d"
                :transform="segment.transform"
                class="organ-heatmap__organ-path"
                :style="segmentStyle(organ.severity, segment)"
              />
            </g>
          </g>

          <path :d="activeLeftArmPath" class="organ-heatmap__outline" :transform="silhouetteTransform" />
          <path :d="activeRightArmPath" class="organ-heatmap__outline" :transform="silhouetteTransform" />
          <path :d="activeBodyPath" class="organ-heatmap__outline" :transform="silhouetteTransform" />
        </g>

        <g v-if="showLegend && !compact" class="organ-heatmap__svg-legend">
          <path
            v-for="row in svgLegendRows"
            :key="`${row.key}-connector`"
            :d="connectorPath(row)"
            class="organ-heatmap__svg-connector"
            :class="legendGroupClass(row.key)"
            :style="connectorStyle(row.severity)"
          />
          <g
            v-for="row in svgLegendRows"
            :key="row.key"
            :class="legendGroupClass(row.key)"
            @click="handleOrganClick(row.key)"
          >
            <rect
              :x="row.x"
              :y="row.y"
              width="92"
              height="40"
              rx="12"
              :style="legendBoxStyle(row.severity)"
            />
            <circle
              :cx="row.x + 14"
              :cy="row.y + 14"
              r="4.5"
              :style="legendDotStyle(row.severity)"
            />
            <text :x="row.x + 24" :y="row.y + 18" class="organ-heatmap__svg-label">{{ row.label }}</text>
            <text :x="row.x + 24" :y="row.y + 31" class="organ-heatmap__svg-status">{{ row.text }}</text>
          </g>
        </g>
      </svg>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useThemeMode } from '../../composables/themeMode'
import {
  BODY_MAP_ORGAN_LABELS,
  BODY_MAP_ORGAN_ORDER,
  bodyMapSeverityText,
  normalizeBodyMapSeverity,
  type BodyMapOrganKey,
  type BodyMapSeverity,
} from '../../utils/bodyMap'

type OrganSegment = {
  d: string
  transform?: string
  fillMode?: 'solid' | 'none'
  fillOpacity?: number
  strokeOpacity?: number
  strokeWidth?: number
  strokeTone?: 'stroke' | 'accent'
  strokeLinecap?: 'butt' | 'round' | 'square'
  strokeLinejoin?: 'miter' | 'round' | 'bevel'
}

const props = withDefaults(defineProps<{
  compact?: boolean
  organStates?: Record<string, any>
  selectedOrgan?: string
  showLegend?: boolean
  organTooltips?: Record<string, any>
  silhouette?: 'female' | 'male'
}>(), {
  compact: false,
  organStates: () => ({}),
  selectedOrgan: '',
  showLegend: false,
  organTooltips: () => ({}),
  silhouette: 'female',
})

const emit = defineEmits<{
  (e: 'organ-click', key: string): void
}>()

const svgUid = `outline-body-${Math.random().toString(36).slice(2, 9)}`
const themeMode = useThemeMode()
const isLightTheme = computed(() => themeMode.value === 'light')

const standingHumanBodyPath = `
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

const standingBodyCorePath = `
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

const emptyArmPath = ''
const femaleBodyPath = standingHumanBodyPath
const maleBodyPath = standingHumanBodyPath
const femaleBodyCorePath = standingBodyCorePath
const maleBodyCorePath = standingBodyCorePath
const femaleLeftArmPath = emptyArmPath
const femaleRightArmPath = emptyArmPath
const maleLeftArmPath = emptyArmPath
const maleRightArmPath = emptyArmPath

const organSegments: Record<BodyMapOrganKey, OrganSegment[]> = {
  neurologic: [
    {
      d: 'M12.2857 42V29.9025C10.5546 28.1181 7.14289 23.6639 7.14282 17.9222C7.14277 13.8404 10.1568 6 21.9823 6C28.0602 6 30.7599 7.4856 33.1299 9.66743C33.2314 9.76084 33.3308 9.85149 33.428 9.94007C34.2801 10.7169 34.9579 11.3349 35.3079 12.2605C36.6082 15.6996 38.9481 20.7122 40.4505 23.8477C41.0916 25.1856 40.1177 26.7437 38.634 26.7437H37.3239V31.5C37.3239 32.6046 36.4285 33.5 35.3239 33.5H32.1154C32.0704 33.4948 32.0246 33.4927 31.9782 33.4937C31.7879 33.4978 31.591 33.4999 31.3887 33.5C31.3812 33.5 31.3738 33.5 31.3663 33.5C30.0936 33.4995 28.6099 33.4198 27.216 33.2741C25.5685 33.1019 24.1404 32.8467 23.3377 32.5587C22.8178 32.3722 22.2452 32.6425 22.0587 33.1623C21.8722 33.6822 22.1425 34.2548 22.6623 34.4413C23.7058 34.8156 25.3373 35.0886 27.0081 35.2632C27.6609 35.3315 28.334 35.3861 29 35.4256V42H12.2857Z',
      transform: 'translate(172 66) scale(1.18)',
      fillOpacity: 0.20,
      strokeWidth: 2.2,
    },
  ],
  respiratory: [
    {
      d: 'M16.542 11.991C22.3921 11.9958 21.8536 19.9527 21.8511 23.1357C21.8478 27.198 22.8451 35.3972 19.7112 38.5181C16.5177 41.6984 10.1346 43.2846 6.94587 40.6296C3.75713 37.9745 9.09663 11.9849 16.542 11.991Z',
      transform: 'translate(142 152) scale(2.4)',
      fillOpacity: 0.16,
      strokeWidth: 2.4,
    },
    {
      d: 'M31.4826 12.0033C25.6326 11.9985 26.158 19.9563 26.1554 23.1392C26.152 27.2016 25.1413 35.3991 28.27 38.5252C31.4583 41.7107 37.8388 43.3074 41.0319 40.6576C44.2249 38.0077 38.928 12.0094 31.4826 12.0033Z',
      transform: 'translate(142 152) scale(2.4)',
      fillOpacity: 0.16,
      strokeWidth: 2.4,
    },
    {
      d: 'M23.0175 5.99927C23.0175 5.99927 23.0175 5.99915 24.0175 5.99997C25.0175 6.00079 25.0175 6.00091 25.0175 6.00091L25.0056 20.4938C25.0039 22.5951 24.0675 23.7995 23.0074 24.4169C22.4404 22.4327 23.0044 21.8892 23.0056 20.4922L23.0175 5.99927Z',
      transform: 'translate(142 152) scale(2.4)',
      fillMode: 'none',
      strokeOpacity: 0.62,
      strokeWidth: 1.9,
      strokeTone: 'accent',
    },
  ],
  circulatory: [
    {
      d: 'M13.281 19.2195C6.01833 25.6975 16.3935 41.8925 24.6938 41.8925C32.994 41.8925 44.4232 25.7119 36.1066 18.2941C35.9147 18.1229 35.7467 17.9689 35.5907 17.8259C34.9033 17.1956 34.4458 16.7762 33.1774 16.022C30.6251 16.022 29.087 18.5751 28.3868 20.1305C28.3512 20.2095 28.3073 20.2832 28.2565 20.3508L26.6423 24.8414L26.0606 26.9296C25.9992 27.1501 26.0152 27.3849 26.1061 27.595L26.7855 29.1652L30.3035 28.7569L30.5341 30.7435L27.2254 31.1276L27.4404 34.2794L25.4451 34.4155L25.1768 30.4837L24.2706 28.3892C23.9979 27.759 23.9497 27.0543 24.1339 26.3929L24.1513 26.3305L22.1173 27.2503L20.7874 30.6121L18.9276 29.8764L19.9809 27.214L16.7704 26.4576L17.229 24.5109L21.2345 25.4546L24.891 23.8009L26.1206 20.3804C22.9526 18.892 16.4469 16.3956 13.281 19.2195Z',
      transform: 'translate(165 192) scale(1.45)',
      fillOpacity: 0.24,
      strokeWidth: 2.3,
    },
    {
      d: 'M20.0003 6H24.0003V8.64383C25.2726 8.56635 26.5058 8.64043 27.6139 8.87435C22.9135 10.7244 20.7509 15.4788 20.3968 16.2574L20.375 16.3051C19.2264 16.1307 17.982 15.9857 16.8045 15.9965C15.5911 16.0999 14.4138 16.2792 12.4749 17.3713C12.2015 17.5645 11.8329 17.8814 11.332 18.3646C11.2956 18.3384 11.2566 18.3141 11.2056 18.2822C11.1648 18.2567 11.1161 18.2264 11.0549 18.1864C10.778 18.0055 10.3737 17.7607 9.8807 17.5162C8.86512 17.0123 7.61933 16.5826 6.39844 16.5826V12.7043C8.50949 12.7043 10.4075 13.421 11.7027 14.0636C12.152 14.2865 12.5463 14.5093 12.8726 14.7073C13.1613 14.0911 13.5422 13.518 13.9976 12.9896L11.801 9.54272L15.322 7.25618L17.3485 10.4363C18.1831 10.0059 19.0783 9.64876 20.0003 9.36808V6Z',
      transform: 'translate(165 192) scale(1.45)',
      fillMode: 'none',
      strokeOpacity: 0.74,
      strokeWidth: 1.8,
      strokeTone: 'accent',
    },
  ],
  hepatic: [
    {
      d: 'M23.2157 10.0607C22.5621 11.0012 22.112 11.962 21.8034 12.8418C21.446 13.8608 21.2754 14.777 21.1939 15.4417C21.153 15.7748 21.1342 16.047 21.1257 16.2402C21.1214 16.3368 21.1197 16.4139 21.1192 16.4692C21.1189 16.4969 21.1189 16.5191 21.1189 16.5356L21.1191 16.556L21.1192 16.563L21.1193 16.5656L21.1193 16.5667C21.1193 16.5667 21.1193 16.5677 22.1191 16.5479C23.1189 16.528 23.1189 16.5288 23.1189 16.5288L23.1189 16.5255L23.1189 16.5227L23.1191 16.4903C23.1194 16.4562 23.1205 16.4015 23.1238 16.3282C23.1302 16.1815 23.1451 15.9615 23.179 15.6853C23.247 15.1312 23.3904 14.3599 23.6907 13.5039C24.0603 12.4502 24.6632 11.2773 25.6539 10.2157C27.9787 10.4791 28.8525 11.0046 29.5758 11.4395C30.2149 11.8238 30.7364 12.1374 32.0374 12.1374C33.3805 12.1374 35.2609 11.7362 37.1413 11.335C39.9619 10.7332 42.7825 10.1315 43.7898 10.8837C45.4687 12.1374 40.432 21.3314 35.3952 21.3314C32.8027 21.3314 31.2481 23.1899 29.7392 24.9937C28.3166 26.6944 26.9347 28.3464 24.762 28.3464C22.6699 28.3464 21.311 29.0047 20 29.7061V23.0479C20 22.6526 20.195 22.2841 20.5335 21.9879C20.8909 21.6752 21.2902 21.5479 21.5 21.5479V19.5479C20.7098 19.5479 19.8591 19.9205 19.2165 20.4828C18.5727 21.0461 18.0298 21.8962 18.0012 22.9597H12.9072C10.5179 22.9597 7.65082 24.0112 10.5179 26.1135C12.5977 27.6385 16.186 26.4249 18 25.6433V30.707C17.0781 31.0885 16.0352 31.3613 14.6885 31.3613C12.8526 31.3613 12.2458 32.8297 11.6009 34.3903C10.8697 36.1599 10.0895 38.0479 7.41312 38.0479C2.37634 38.0479 3.61914 22.5479 6.61916 16.5479C9.61919 10.5479 13.7245 10.0479 22.1192 10.0479C22.5059 10.0479 22.8709 10.0523 23.2157 10.0607Z',
      transform: 'translate(163 258) scale(2.05)',
      fillOpacity: 0.18,
      strokeWidth: 2.2,
    },
    {
      d: 'M18 40.0479V30.707L20 29.7061V40.0479H18Z',
      transform: 'translate(163 258) scale(2.05)',
      fillMode: 'none',
      strokeOpacity: 0.58,
      strokeWidth: 1.6,
      strokeTone: 'accent',
    },
  ],
  coagulation: [
    {
      d: 'M24 4L23.3098 4.66021L23.3061 4.6638L23.2973 4.67227L23.2648 4.70366C23.2367 4.73095 23.1956 4.7709 23.1426 4.82303C23.0366 4.92728 22.8826 5.08029 22.6874 5.27827C22.297 5.67417 21.7417 6.25029 21.0763 6.97632C19.7465 8.42723 17.9719 10.4826 16.1951 12.8995C12.6815 17.6788 9 24.0809 9 30.0801C9 37.845 15.796 44 24 44C32.204 44 39 37.845 39 30.0801C39 24.0809 35.3185 17.6788 31.8049 12.8995C30.0281 10.4826 28.2535 8.42723 26.9237 6.97632C26.2583 6.25029 25.703 5.67417 25.3126 5.27827C25.1174 5.08029 24.9634 4.92728 24.8574 4.82303C24.8044 4.7709 24.7634 4.73095 24.7352 4.70366L24.7027 4.67227L24.6939 4.6638L24.6902 4.66021L24 4ZM15.4649 31.3985C15.2943 30.8716 14.7301 30.5833 14.2049 30.7545C13.6796 30.9257 13.3922 31.4915 13.5628 32.0183C14.3133 34.3349 15.7757 36.3536 17.7404 37.7853C19.7052 39.217 22.0714 39.9882 24.5 39.9882C25.0523 39.9882 25.5 39.5391 25.5 38.9852C25.5 38.4313 25.0523 37.9822 24.5 37.9822C22.4938 37.9822 20.5391 37.3452 18.916 36.1625C17.293 34.9798 16.0849 33.3121 15.4649 31.3985Z',
      transform: 'translate(177 198) scale(0.95)',
      fillOpacity: 0.12,
      strokeOpacity: 0.88,
      strokeWidth: 2.4,
    },
    {
      d: 'M17.9996 6V25.3798L15.0743 23.36L15.166 23.3499L14.2005 14.5931L12.2125 14.8123L12.9968 21.9255L6.37998 17.3567L4.87305 23.3844L9.29292 26.8736L5.23806 27.8952L5.72665 29.8346L11.2735 28.4371L17.6221 33.4489L17.6283 33.4537C17.8607 33.6313 17.9996 33.9105 17.9996 34.2095V42H27.9996V27.1135C27.9996 26.7783 28.1896 26.455 28.519 26.2841L33.67 23.6112L41.2632 25.4582L41.736 23.5148L36.2978 22.192L42.2777 18.9437L40.0094 13.651L32.4333 17.2479L33.4762 12.5124L31.523 12.0822L30.143 18.3481L27.9996 19.4295V6H17.9996ZM23.2265 8.84951C23.5179 9.31868 23.3738 9.93522 22.9046 10.2266C22.4354 10.518 21.8189 10.3738 21.5275 9.90467C21.2361 9.4355 21.3803 8.81896 21.8494 8.52759C22.3186 8.23621 22.9352 8.38034 23.2265 8.84951ZM24.9046 14.2266C25.3738 13.9352 25.5179 13.3187 25.2265 12.8495C24.9352 12.3803 24.3186 12.2362 23.8494 12.5276C23.3803 12.819 23.2361 13.4355 23.5275 13.9047C23.8189 14.3738 24.4354 14.518 24.9046 14.2266ZM22.9046 23.2266C23.3738 22.9352 23.5179 22.3187 23.2265 21.8495C22.9352 21.3803 22.3186 21.2362 21.8494 21.5276C21.3803 21.819 21.2361 22.4355 21.5275 22.9047C21.8189 23.3738 22.4354 23.518 22.9046 23.2266ZM24.2265 28.8495C24.5179 29.3187 24.3738 29.9352 23.9046 30.2266C23.4354 30.518 22.8189 30.3738 22.5275 29.9047C22.2361 29.4355 22.3803 28.819 22.8494 28.5276C23.3186 28.2362 23.9352 28.3803 24.2265 28.8495ZM22.9046 39.2266C23.3738 38.9352 23.5179 38.3187 23.2265 37.8495C22.9352 37.3803 22.3186 37.2362 21.8494 37.5276C21.3803 37.819 21.2361 38.4355 21.5275 38.9047C21.8189 39.3738 22.4354 39.518 22.9046 39.2266Z',
      transform: 'translate(170 233) scale(0.78)',
      fillOpacity: 0.1,
      strokeOpacity: 0.84,
      strokeWidth: 2.1,
    },
  ],
  renal: [
    {
      d: 'M12.548 30.7532C1.68377 26.171 5.97137 10.7042 13.513 8.14865C16.6416 7.08852 20.0938 10.6056 20.0717 12.7893C20.0621 13.7335 19.5749 14.6541 19.0673 15.6132C18.4009 16.8725 17.6993 18.1982 17.9972 19.7308C18.5221 22.4309 19.11 26.9868 17.5952 29.1494C16.0803 31.312 14.5569 31.6005 12.548 30.7532Z',
      transform: 'translate(152 310) scale(2)',
      fillOpacity: 0.17,
      strokeWidth: 2.2,
    },
    {
      d: 'M34.3473 8.14865C41.889 10.7042 46.1766 26.171 35.3124 30.7532C33.3034 31.6005 31.78 31.312 30.2652 29.1494C28.7504 26.9868 29.3383 22.4309 29.8631 19.7308C30.161 18.1982 29.4595 16.8725 28.793 15.6132C28.2854 14.6541 27.7982 13.7335 27.7887 12.7893C27.7666 10.6056 31.2188 7.08852 34.3473 8.14865Z',
      transform: 'translate(152 310) scale(2)',
      fillOpacity: 0.17,
      strokeWidth: 2.2,
    },
    {
      d: 'M19.2423 22.7796C19.1737 23.7773 19.173 23.7772 19.1724 23.7772L19.1713 23.7771L19.169 23.7769L19.1652 23.7766L19.1596 23.7762C19.1577 23.776 19.1567 23.7759 19.1565 23.7759C19.1582 23.7761 19.167 23.7771 19.1812 23.7794C19.21 23.784 19.2603 23.7936 19.3246 23.8118C19.4557 23.849 19.6285 23.917 19.7978 24.0376C20.0875 24.2439 20.5135 24.7021 20.5135 25.8583V40.3244C20.5135 40.3245 20.5135 40.3245 21.5135 40.3245C22.5135 40.3245 22.5135 40.3241 22.5135 40.324V25.8583C22.5135 24.0919 21.8038 23.0108 20.9579 22.4084C20.5594 22.1246 20.1644 21.971 19.8696 21.8875C19.7211 21.8454 19.5939 21.82 19.4985 21.8047C19.4506 21.797 19.4103 21.7918 19.3787 21.7883C19.3629 21.7865 19.3493 21.7851 19.3379 21.7841L19.3226 21.7828L19.3163 21.7824L19.3135 21.7822L19.3121 21.7821C19.3115 21.782 19.3108 21.782 19.2423 22.7796Z',
      transform: 'translate(152 310) scale(2)',
      fillMode: 'none',
      strokeOpacity: 0.56,
      strokeWidth: 1.5,
      strokeTone: 'accent',
    },
  ],
}

const organRenderOrder: BodyMapOrganKey[] = [
  'neurologic',
  'respiratory',
  'hepatic',
  'renal',
  'coagulation',
  'circulatory',
]

const renderedOrgans = computed(() =>
  organRenderOrder.map((key) => ({
    key,
    label: BODY_MAP_ORGAN_LABELS[key],
    severity: normalizeBodyMapSeverity(props.organStates?.[key]),
    segments: organSegments[key],
  }))
)

const legendRows = computed(() =>
  BODY_MAP_ORGAN_ORDER.map((key) => ({
    key,
    label: BODY_MAP_ORGAN_LABELS[key],
    severity: normalizeBodyMapSeverity(props.organStates?.[key]),
    text: bodyMapSeverityText(props.organStates?.[key]),
  }))
)

const organAnchors: Record<BodyMapOrganKey, { x: number; y: number }> = {
  neurologic: { x: 201, y: 78 },
  respiratory: { x: 200, y: 214 },
  circulatory: { x: 198, y: 212 },
  hepatic: { x: 212, y: 308 },
  coagulation: { x: 202, y: 192 },
  renal: { x: 200, y: 352 },
}

const svgLegendRows = computed(() => {
  const yPositions = [134, 202, 270, 338, 406, 474]
  return legendRows.value.map((row, index) => ({
    ...row,
    x: 294,
    y: yPositions[index] ?? 134 + index * 68,
  }))
})

const severityPalette: Record<BodyMapSeverity, { fill: string; stroke: string; accent: string }> = {
  normal: { fill: '#22c55e', stroke: '#bbf7d0', accent: '#86efac' },
  warning: { fill: '#fbbf24', stroke: '#fde68a', accent: '#fcd34d' },
  high: { fill: '#fb923c', stroke: '#fed7aa', accent: '#fdba74' },
  critical: { fill: '#ef4444', stroke: '#fecaca', accent: '#fda4af' },
}

const organLayerOffset = { x: -2, y: 4 }

const activeBodyPath = computed(() => props.silhouette === 'male' ? maleBodyPath : femaleBodyPath)
const activeBodyCorePath = computed(() => props.silhouette === 'male' ? maleBodyCorePath : femaleBodyCorePath)
const activeLeftArmPath = computed(() => props.silhouette === 'male' ? maleLeftArmPath : femaleLeftArmPath)
const activeRightArmPath = computed(() => props.silhouette === 'male' ? maleRightArmPath : femaleRightArmPath)
const silhouetteTransform = 'matrix(3.15 0 0 3.15 -128 24)'
const organLayerTransform = `translate(${organLayerOffset.x} ${organLayerOffset.y})`
const figureTransform = computed(() =>
  props.showLegend && !props.compact
    ? 'matrix(0.94 0 0 0.94 -30 12)'
    : 'translate(0 0)'
)

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

function segmentStyle(severity: string, segment: OrganSegment) {
  const palette = paletteFor(severity)
  const strokeHex = segment.strokeTone === 'accent' ? palette.accent : palette.stroke
  return {
    fill: segment.fillMode === 'none' ? 'none' : rgba(palette.fill, segment.fillOpacity ?? 0.18),
    stroke: rgba(strokeHex, segment.strokeOpacity ?? 0.92),
    strokeWidth: `${segment.strokeWidth ?? 2}px`,
    strokeLinecap: segment.strokeLinecap || 'round',
    strokeLinejoin: segment.strokeLinejoin || 'round',
  }
}

function organGroupClass(key: string, severity: string) {
  return [
    'organ-heatmap__organ',
    `is-${severity}`,
    {
      'is-selected': props.selectedOrgan === key,
      'is-dimmed': props.selectedOrgan && props.selectedOrgan !== key,
      'is-pulse': severity === 'high' || severity === 'critical',
    },
  ]
}

function legendGroupClass(key: string) {
  return [
    'organ-heatmap__svg-legend-item',
    {
      'is-selected': props.selectedOrgan === key,
      'is-dimmed': props.selectedOrgan && props.selectedOrgan !== key,
    },
  ]
}

function legendBoxStyle(severity: string) {
  const palette = paletteFor(severity)
  return {
    fill: isLightTheme.value ? rgba('#f8fbff', 0.94) : rgba('#091626', 0.76),
    stroke: rgba(palette.fill, isLightTheme.value ? 0.28 : 0.38),
    strokeWidth: '1.1px',
  }
}

function legendDotStyle(severity: string) {
  const palette = paletteFor(severity)
  return {
    fill: palette.fill,
    stroke: rgba(palette.stroke, isLightTheme.value ? 0.84 : 0.92),
    strokeWidth: '0.8px',
  }
}

function connectorStyle(severity: string) {
  const palette = paletteFor(severity)
  return {
    stroke: rgba(palette.fill, 0.34),
    strokeWidth: '1.4px',
  }
}

function transformedX(value: number) {
  return props.showLegend && !props.compact ? value * 0.94 - 30 : value
}

function transformedY(value: number) {
  return props.showLegend && !props.compact ? value * 0.94 + 12 : value
}

function connectorPath(row: { key: BodyMapOrganKey; x: number; y: number }) {
  const anchor = organAnchors[row.key]
  const fromX = transformedX(anchor.x + organLayerOffset.x)
  const fromY = transformedY(anchor.y + organLayerOffset.y)
  const toX = row.x - 8
  const toY = row.y + 20
  const midX = fromX + 34
  return `M ${fromX} ${fromY} C ${midX} ${fromY}, ${toX - 18} ${toY}, ${toX} ${toY}`
}

function organTitle(key: BodyMapOrganKey, severity: string) {
  const text = bodyMapSeverityText(severity)
  const tooltip = props.organTooltips?.[key]
  const detail = typeof tooltip?.detail === 'string' && tooltip.detail.trim()
    ? `：${tooltip.detail.trim()}`
    : ''
  return `${BODY_MAP_ORGAN_LABELS[key]}（${text}）${detail}`
}

function handleOrganClick(key: BodyMapOrganKey) {
  emit('organ-click', key)
}
</script>

<style scoped>
.organ-heatmap {
  display: grid;
}

.organ-heatmap__frame {
  position: relative;
  width: min(100%, 400px);
  margin: 0 auto;
}

.organ-heatmap--compact .organ-heatmap__frame {
  width: min(100%, 250px);
}

.organ-heatmap__svg {
  display: block;
  width: 100%;
  height: auto;
  border-radius: 20px;
  overflow: hidden;
  background: #0a1628;
}

.organ-heatmap__figure,
.organ-heatmap__organs {
  isolation: isolate;
}

.organ-heatmap__body,
.organ-heatmap__core,
.organ-heatmap__outline,
.organ-heatmap__organ-path,
.organ-heatmap__svg-connector {
  stroke-linecap: round;
  stroke-linejoin: round;
}

.organ-heatmap__body--glow {
  fill: rgba(122, 244, 255, 0.16);
  opacity: 0.92;
}

.organ-heatmap__body {
  stroke: rgba(147, 244, 255, 0.30);
  stroke-width: 2;
}

.organ-heatmap__core {
  stroke: rgba(180, 250, 255, 0.08);
  stroke-width: 1;
}

.organ-heatmap__outline {
  fill: none;
  stroke: rgba(152, 244, 255, 0.42);
  stroke-width: 1.5;
}

.organ-heatmap__organ {
  cursor: pointer;
  mix-blend-mode: screen;
  transform-origin: center;
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.organ-heatmap__organ:hover,
.organ-heatmap__organ.is-selected {
  transform: scale(1.03);
}

.organ-heatmap__organ.is-dimmed {
  opacity: 0.42;
}

.organ-heatmap__organ-path {
  vector-effect: non-scaling-stroke;
}

.organ-heatmap__organ.is-pulse {
  animation: organPulse 2s ease-in-out infinite;
}

.organ-heatmap__svg-connector {
  fill: none;
  opacity: 0.72;
  transition: opacity .2s ease, stroke .2s ease;
}

.organ-heatmap__svg-legend-item {
  cursor: pointer;
  transition: opacity .2s ease, transform .2s ease;
  transform-origin: center;
}

.organ-heatmap__svg-legend-item:hover,
.organ-heatmap__svg-legend-item.is-selected {
  transform: translateX(-2px);
}

.organ-heatmap__svg-legend-item.is-dimmed,
.organ-heatmap__svg-connector.is-dimmed {
  opacity: .42;
}

.organ-heatmap__svg-label,
.organ-heatmap__svg-status {
  pointer-events: none;
  user-select: none;
}

.organ-heatmap__svg-label {
  fill: rgba(236, 251, 255, .96);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: .04em;
}

.organ-heatmap__svg-status {
  fill: rgba(146, 207, 221, .88);
  font-size: 10px;
  font-weight: 600;
}

@keyframes organPulse {
  0%, 100% {
    opacity: 0.96;
  }
  50% {
    opacity: 0.72;
  }
}

html[data-theme='light'] .organ-heatmap__svg {
  background: #f1f7fc;
}

html[data-theme='light'] .organ-heatmap__svg-stop--bg-0 {
  stop-color: #f7fbff !important;
}

html[data-theme='light'] .organ-heatmap__svg-stop--bg-58 {
  stop-color: #ecf4fb !important;
}

html[data-theme='light'] .organ-heatmap__svg-stop--bg-100 {
  stop-color: #e5eef8 !important;
}

html[data-theme='light'] .organ-heatmap__svg-stop--body-0 {
  stop-color: #5ec7e5 !important;
  stop-opacity: 0.2 !important;
}

html[data-theme='light'] .organ-heatmap__svg-stop--body-45 {
  stop-color: #47b8da !important;
  stop-opacity: 0.16 !important;
}

html[data-theme='light'] .organ-heatmap__svg-stop--body-100 {
  stop-color: #2e94bf !important;
  stop-opacity: 0.1 !important;
}

html[data-theme='light'] .organ-heatmap__svg-stop--core-0 {
  stop-color: #d5ecfa !important;
  stop-opacity: 0.32 !important;
}

html[data-theme='light'] .organ-heatmap__svg-stop--core-100 {
  stop-color: #95c9e8 !important;
  stop-opacity: 0.08 !important;
}

html[data-theme='light'] .organ-heatmap__body--glow {
  fill: rgba(74, 165, 204, 0.14);
}

html[data-theme='light'] .organ-heatmap__body {
  stroke: rgba(90, 156, 193, 0.42);
}

html[data-theme='light'] .organ-heatmap__core {
  stroke: rgba(110, 166, 196, 0.2);
}

html[data-theme='light'] .organ-heatmap__outline {
  stroke: rgba(93, 152, 186, 0.52);
}

html[data-theme='light'] .organ-heatmap__organ {
  mix-blend-mode: multiply;
}

html[data-theme='light'] .organ-heatmap__svg-label {
  fill: #264763;
}

html[data-theme='light'] .organ-heatmap__svg-status {
  fill: #5a7a93;
}

html[data-theme='light'] .organ-heatmap__svg-connector {
  opacity: 0.78;
}
</style>
