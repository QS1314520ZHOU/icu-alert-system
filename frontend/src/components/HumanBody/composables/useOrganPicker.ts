// @vitest-skip: requires WebGL
import * as THREE from 'three'
import type { OrganBusinessName } from '../../../types/organ'

export type OrganPickerOptions = {
  container: HTMLElement
  camera: THREE.Camera
  meshes: () => THREE.Mesh[]
  onPick: (businessName: OrganBusinessName, mesh: THREE.Mesh) => void
}

export function useOrganPicker(options: OrganPickerOptions) {
  const raycaster = new THREE.Raycaster()
  const pointer = new THREE.Vector2()

  function onPointerDown(event: PointerEvent) {
    const rect = options.container.getBoundingClientRect()
    if (rect.width <= 0 || rect.height <= 0) return
    pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1
    pointer.y = -(((event.clientY - rect.top) / rect.height) * 2 - 1)
    raycaster.setFromCamera(pointer, options.camera)

    const intersections = raycaster.intersectObjects(options.meshes(), false)
    const hit = intersections.find(item => Boolean((item.object as THREE.Mesh).userData.pickable))
    if (!hit) return
    const mesh = hit.object as THREE.Mesh
    const businessName = mesh.userData.businessName as OrganBusinessName | undefined
    if (!businessName) return
    options.onPick(businessName, mesh)
  }

  options.container.addEventListener('pointerdown', onPointerDown, { passive: true })

  return {
    dispose() {
      options.container.removeEventListener('pointerdown', onPointerDown)
    },
  }
}
