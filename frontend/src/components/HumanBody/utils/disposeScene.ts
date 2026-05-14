// @vitest-skip: requires WebGL
import type { BufferGeometry, Material, Object3D, Scene, Texture, WebGLRenderer } from 'three'

type DisposableControls = {
  dispose?: () => void
}

function disposeMaterial(material: Material) {
  Object.values(material as unknown as Record<string, unknown>).forEach((value) => {
    if (value && typeof value === 'object' && 'isTexture' in value) {
      ;(value as Texture).dispose()
    }
  })
  material.dispose()
}

function disposeObject(object: Object3D) {
  const mesh = object as Object3D & {
    geometry?: BufferGeometry
    material?: Material | Material[]
  }

  mesh.geometry?.dispose()
  if (Array.isArray(mesh.material)) {
    mesh.material.forEach(disposeMaterial)
  } else if (mesh.material) {
    disposeMaterial(mesh.material)
  }
}

export function disposeScene(scene: Scene, renderer?: WebGLRenderer | null, controls?: DisposableControls | null) {
  scene.traverse(disposeObject)
  while (scene.children.length > 0) {
    const child = scene.children[0]
    if (!child) break
    scene.remove(child)
  }
  controls?.dispose?.()
  renderer?.dispose()
  renderer?.forceContextLoss?.()
}
