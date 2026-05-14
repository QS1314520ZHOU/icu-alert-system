<template>
  <div ref="containerRef" class="human-body-3d">
    <div v-if="loading" class="human-body-3d__status">加载人体模型...</div>
    <div v-if="errorMessage" class="human-body-3d__status human-body-3d__status--error">{{ errorMessage }}</div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as THREE from 'three'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { DRACOLoader } from 'three/examples/jsm/loaders/DRACOLoader.js'
import { ORGAN_MAP, meshToBusinessName } from './constants/organMap'
import { useThreeScene } from './composables/useThreeScene'
import { useOrganPicker } from './composables/useOrganPicker'
import { useAlarmHighlight } from './composables/useAlarmHighlight'
import { useCameraFocus } from './composables/useCameraFocus'
import { useHumanBodyAlarmStore } from '../../stores/humanBodyAlarmStore'
import { connectHumanBodyAlarmAdapter } from '../../services/humanBodyAlarmAdapter'
import type { HumanBodyAlarmRecord } from '../../types/alarm'
import type { OrganBusinessName } from '../../types/organ'

const props = withDefaults(defineProps<{
  model?: 'high' | 'low'
  patientId?: string
  autoFocus?: boolean
  showLabels?: boolean
}>(), {
  model: 'high',
  autoFocus: true,
  showLabels: true,
})

const emit = defineEmits<{
  ready: [organs: OrganBusinessName[]]
  'load-failed': [reason: string]
  'organ-click': [businessName: OrganBusinessName]
}>()

type SceneHandle = ReturnType<typeof useThreeScene>

const containerRef = ref<HTMLElement | null>(null)
const loading = ref(true)
const errorMessage = ref('')
const organMeshes = new Map<OrganBusinessName, THREE.Mesh>()
const store = useHumanBodyAlarmStore()
const visibleAlarms = computed(() => {
  return props.patientId ? store.getAlarmsByPatient(props.patientId) : store.getAggregatedAlarms()
})
let sceneHandle: SceneHandle | null = null
let picker: ReturnType<typeof useOrganPicker> | null = null
let highlighter: ReturnType<typeof useAlarmHighlight> | null = null
let cameraFocus: ReturnType<typeof useCameraFocus> | null = null
let offAlarmAdapter: (() => void) | null = null
let animationFrame = 0
let disposed = false
let lastFocusedKey = ''

function modelPath() {
  return props.model === 'low' ? '/models/human_low.glb' : '/models/human_high.glb'
}

function registerOrganMesh(organ: OrganBusinessName, mesh: THREE.Mesh) {
  mesh.name = ORGAN_MAP[organ].mesh
  mesh.userData.businessName = organ
  mesh.userData.pickable = true
  organMeshes.set(organ, mesh)
}

function createMaterial(color: number, opacity = 0.86) {
  return new THREE.MeshStandardMaterial({
    color,
    roughness: 0.64,
    metalness: 0.05,
    transparent: true,
    opacity,
  })
}

function createPlaceholderOrgan(
  organ: OrganBusinessName,
  geometry: THREE.BufferGeometry,
  position: [number, number, number],
  scale: [number, number, number],
  color: number,
) {
  const mesh = new THREE.Mesh(geometry, createMaterial(color))
  mesh.position.set(...position)
  mesh.scale.set(...scale)
  registerOrganMesh(organ, mesh)
  return mesh
}

function initializeInteraction() {
  if (!sceneHandle || !containerRef.value || highlighter) return
  highlighter = useAlarmHighlight(organ => organMeshes.get(organ))
  cameraFocus = useCameraFocus({
    camera: sceneHandle.camera,
    controls: sceneHandle.controls,
  })
  picker = useOrganPicker({
    container: containerRef.value,
    camera: sceneHandle.camera,
    meshes: () => [...organMeshes.values()],
    onPick: (businessName, mesh) => {
      emit('organ-click', businessName)
      highlighter?.setHighlight(businessName, 'selected')
      cameraFocus?.focusOn(mesh)
      window.setTimeout(() => {
        const alarmLevel = visibleAlarms.value.find(item => item.organ === businessName)?.level || null
        highlighter?.setHighlight(businessName, alarmLevel)
      }, 1200)
    },
  })
  syncAlarmHighlights(visibleAlarms.value)
}

function syncAlarmHighlights(records: HumanBodyAlarmRecord[]) {
  if (!highlighter) return
  const activeOrgans = new Set(records.map(item => item.organ))
  organMeshes.forEach((_, organ) => {
    const alarm = records.find(item => item.organ === organ)
    highlighter?.setHighlight(organ, alarm?.level || null)
  })
  const highest = records[0]
  const focusKey = highest ? `${highest.organ}:${highest.level}:${highest.timestamp}` : ''
  if (props.autoFocus && highest && activeOrgans.has(highest.organ) && focusKey !== lastFocusedKey) {
    const mesh = organMeshes.get(highest.organ)
    if (mesh) {
      cameraFocus?.focusOn(mesh)
      lastFocusedKey = focusKey
    }
  }
}

function createPlaceholderBody() {
  if (!sceneHandle) return
  const group = new THREE.Group()
  group.name = 'HumanBodyPlaceholder'

  const bodyMaterial = createMaterial(0x28435c, 0.28)
  const torso = new THREE.Mesh(new THREE.CapsuleGeometry(0.82, 1.9, 12, 24), bodyMaterial)
  torso.position.set(0, 0.35, 0)
  group.add(torso)

  group.add(createPlaceholderOrgan('brain', new THREE.SphereGeometry(0.34, 32, 16), [0, 1.92, 0], [1, 0.78, 0.92], 0xa9d6ff))
  group.add(createPlaceholderOrgan('heart', new THREE.SphereGeometry(0.2, 32, 16), [0.05, 0.82, 0.28], [0.9, 1.05, 0.75], 0xff6b7a))
  group.add(createPlaceholderOrgan('left_lung', new THREE.CapsuleGeometry(0.2, 0.58, 10, 18), [-0.28, 0.86, 0.14], [0.82, 1, 0.58], 0x7fd5ff))
  group.add(createPlaceholderOrgan('right_lung', new THREE.CapsuleGeometry(0.2, 0.58, 10, 18), [0.32, 0.86, 0.14], [0.82, 1, 0.58], 0x7fd5ff))
  group.add(createPlaceholderOrgan('liver', new THREE.BoxGeometry(0.56, 0.24, 0.26), [0.24, 0.26, 0.22], [1, 1, 1], 0xc58b4a))
  group.add(createPlaceholderOrgan('stomach', new THREE.SphereGeometry(0.2, 28, 14), [-0.28, 0.19, 0.2], [0.88, 1.15, 0.62], 0xe6a1c6))
  group.add(createPlaceholderOrgan('spleen', new THREE.SphereGeometry(0.14, 24, 12), [-0.55, 0.28, 0.16], [0.72, 1.2, 0.5], 0xb278d6))
  group.add(createPlaceholderOrgan('pancreas', new THREE.BoxGeometry(0.48, 0.1, 0.12), [-0.05, 0.08, 0.28], [1, 1, 1], 0xf1c27d))
  group.add(createPlaceholderOrgan('left_kidney', new THREE.SphereGeometry(0.16, 24, 12), [-0.35, -0.22, -0.06], [0.74, 1.1, 0.5], 0xd36b4b))
  group.add(createPlaceholderOrgan('right_kidney', new THREE.SphereGeometry(0.16, 24, 12), [0.35, -0.22, -0.06], [0.74, 1.1, 0.5], 0xd36b4b))
  group.add(createPlaceholderOrgan('intestine', new THREE.TorusKnotGeometry(0.22, 0.055, 80, 8), [0, -0.56, 0.2], [1.1, 0.8, 0.72], 0xf0b36f))
  group.add(createPlaceholderOrgan('bladder', new THREE.SphereGeometry(0.16, 24, 12), [0, -1.02, 0.12], [0.9, 0.78, 0.7], 0xffdf7e))

  sceneHandle.scene.add(group)
  loading.value = false
  initializeInteraction()
  emit('ready', [...organMeshes.keys()])
}

function indexLoadedModel(root: THREE.Object3D) {
  root.traverse((object) => {
    const mesh = object as THREE.Mesh
    if (!mesh.isMesh) return
    const organ = meshToBusinessName(mesh.name)
    if (!organ) {
      mesh.userData.pickable = false
      return
    }
    mesh.userData.businessName = organ
    mesh.userData.pickable = true
    organMeshes.set(organ, mesh)
  })
}

async function loadGlbWithTimeout() {
  const loader = new GLTFLoader()
  const draco = new DRACOLoader()
  draco.setDecoderPath('/draco/')
  loader.setDRACOLoader(draco)

  const timeout = new Promise<never>((_, reject) => {
    window.setTimeout(() => reject(new Error('GLB load timeout')), 5000)
  })
  const gltf = await Promise.race([loader.loadAsync(modelPath()), timeout])
  draco.dispose()
  return gltf
}

async function loadBodyModel() {
  if (!sceneHandle) return
  try {
    const gltf = await loadGlbWithTimeout()
    sceneHandle.scene.add(gltf.scene)
    indexLoadedModel(gltf.scene)
    if (organMeshes.size < Object.keys(ORGAN_MAP).length) {
      console.info(`[human-body] recognized ${organMeshes.size} organs from GLB, using placeholder for missing organs`)
    } else {
      console.info(`[human-body] recognized organs: ${[...organMeshes.keys()].join(', ')}`)
    }
    loading.value = false
    initializeInteraction()
    emit('ready', [...organMeshes.keys()])
  } catch (error) {
    const reason = error instanceof Error ? error.message : 'GLB load failed'
    console.warn(`[human-body] ${reason}; using procedural placeholder`)
    errorMessage.value = '使用简化人体模型'
    emit('load-failed', reason)
    createPlaceholderBody()
  }
}

function animate() {
  if (!sceneHandle || disposed) return
  sceneHandle.controls.update()
  highlighter?.update(performance.now() / 1000)
  sceneHandle.renderer.render(sceneHandle.scene, sceneHandle.camera)
  animationFrame = window.requestAnimationFrame(animate)
}

onMounted(() => {
  if (!containerRef.value) return
  sceneHandle = useThreeScene(containerRef.value)
  offAlarmAdapter = connectHumanBodyAlarmAdapter()
  void loadBodyModel()
  animate()
})

watch(visibleAlarms, records => syncAlarmHighlights(records), { deep: true })

onBeforeUnmount(() => {
  disposed = true
  if (animationFrame) window.cancelAnimationFrame(animationFrame)
  offAlarmAdapter?.()
  picker?.dispose()
  highlighter?.dispose()
  cameraFocus?.dispose()
  organMeshes.clear()
  sceneHandle?.dispose()
  sceneHandle = null
})
</script>

<style scoped>
.human-body-3d {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 320px;
  overflow: hidden;
  background: #05070a;
}

.human-body-3d__status {
  position: absolute;
  left: 12px;
  top: 12px;
  z-index: 2;
  padding: 6px 10px;
  border: 1px solid rgba(117, 211, 255, 0.28);
  border-radius: 4px;
  color: #cfefff;
  background: rgba(5, 12, 20, 0.74);
  font-size: 12px;
}

.human-body-3d__status--error {
  top: 46px;
  color: #ffd88a;
}
</style>
