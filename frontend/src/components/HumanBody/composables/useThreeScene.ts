// @vitest-skip: requires WebGL
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { disposeScene } from '../utils/disposeScene'

export type ThreeSceneOptions = {
  background?: number
  cameraFov?: number
  minDistance?: number
  maxDistance?: number
}

export function useThreeScene(container: HTMLElement, options: ThreeSceneOptions = {}) {
  const width = Math.max(container.clientWidth, 1)
  const height = Math.max(container.clientHeight, 1)
  const scene = new THREE.Scene()
  scene.background = new THREE.Color(options.background ?? 0x05070a)

  const camera = new THREE.PerspectiveCamera(options.cameraFov ?? 38, width / height, 0.1, 1000)
  camera.position.set(0, 1.5, 6.5)

  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, powerPreference: 'high-performance' })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
  renderer.setSize(width, height)
  renderer.outputColorSpace = THREE.SRGBColorSpace
  renderer.shadowMap.enabled = false
  container.appendChild(renderer.domElement)

  const controls = new OrbitControls(camera, renderer.domElement)
  controls.enableDamping = true
  controls.dampingFactor = 0.08
  controls.minDistance = options.minDistance ?? 2
  controls.maxDistance = options.maxDistance ?? 12
  controls.target.set(0, 0.9, 0)

  scene.add(new THREE.AmbientLight(0xffffff, 0.75))
  const keyLight = new THREE.DirectionalLight(0xffffff, 1.1)
  keyLight.position.set(4, 6, 5)
  scene.add(keyLight)
  const fillLight = new THREE.DirectionalLight(0x9ecbff, 0.45)
  fillLight.position.set(-4, 2, -4)
  scene.add(fillLight)

  function resize() {
    const nextWidth = Math.max(container.clientWidth, 1)
    const nextHeight = Math.max(container.clientHeight, 1)
    camera.aspect = nextWidth / nextHeight
    camera.updateProjectionMatrix()
    renderer.setSize(nextWidth, nextHeight)
  }

  window.addEventListener('resize', resize, { passive: true })

  function dispose() {
    window.removeEventListener('resize', resize)
    renderer.domElement.remove()
    disposeScene(scene, renderer, controls)
  }

  return {
    scene,
    camera,
    renderer,
    controls,
    resize,
    dispose,
  }
}
