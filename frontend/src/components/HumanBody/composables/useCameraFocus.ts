// @vitest-skip: requires WebGL
import * as THREE from 'three'
import { gsap } from 'gsap'
import type { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'

export type CameraFocusOptions = {
  camera: THREE.PerspectiveCamera
  controls: OrbitControls
  duration?: number
}

export function useCameraFocus(options: CameraFocusOptions) {
  const defaultPosition = options.camera.position.clone()
  const defaultTarget = options.controls.target.clone()
  const duration = options.duration ?? 1.2

  function tweenTo(position: THREE.Vector3, target: THREE.Vector3) {
    gsap.killTweensOf(options.camera.position)
    gsap.killTweensOf(options.controls.target)
    gsap.to(options.camera.position, {
      x: position.x,
      y: position.y,
      z: position.z,
      duration,
      ease: 'power2.out',
      onUpdate: () => options.camera.updateProjectionMatrix(),
    })
    gsap.to(options.controls.target, {
      x: target.x,
      y: target.y,
      z: target.z,
      duration,
      ease: 'power2.out',
      onUpdate: () => options.controls.update(),
    })
  }

  function focusOn(mesh: THREE.Object3D) {
    const box = new THREE.Box3().setFromObject(mesh)
    if (box.isEmpty()) return
    const size = box.getSize(new THREE.Vector3())
    const center = box.getCenter(new THREE.Vector3())
    const maxSize = Math.max(size.x, size.y, size.z, 0.2)
    const fov = THREE.MathUtils.degToRad(options.camera.fov)
    const distance = Math.max((maxSize / (2 * Math.tan(fov / 2))) * 1.65, 1.4)
    const direction = new THREE.Vector3(0.25, 0.2, 1).normalize()
    const position = center.clone().add(direction.multiplyScalar(distance))
    tweenTo(position, center)
  }

  function resetView() {
    tweenTo(defaultPosition, defaultTarget)
  }

  function dispose() {
    gsap.killTweensOf(options.camera.position)
    gsap.killTweensOf(options.controls.target)
  }

  return {
    focusOn,
    resetView,
    dispose,
  }
}
