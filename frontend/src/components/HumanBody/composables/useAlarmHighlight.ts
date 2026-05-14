// @vitest-skip: requires WebGL
import * as THREE from 'three'
import { ALARM_LEVELS } from '../constants/alarmLevels'
import type { HumanBodyAlarmLevel } from '../../../types/alarm'
import type { OrganBusinessName } from '../../../types/organ'

type HighlightState = {
  mesh: THREE.Mesh
  level: HumanBodyAlarmLevel
  material: THREE.MeshStandardMaterial
  phase: number
}

type MeshLookup = (businessName: OrganBusinessName) => THREE.Mesh | undefined

function cloneMaterial(level: HumanBodyAlarmLevel) {
  const config = ALARM_LEVELS[level]
  return new THREE.MeshStandardMaterial({
    color: config.color,
    emissive: config.emissive,
    emissiveIntensity: level === 'selected' ? 0.45 : 0.85,
    roughness: 0.42,
    metalness: 0.08,
    transparent: true,
    opacity: 0.96,
  })
}

function disposeMaterial(material: THREE.Material | THREE.Material[]) {
  if (Array.isArray(material)) {
    material.forEach(item => item.dispose())
    return
  }
  material.dispose()
}

export function useAlarmHighlight(getMesh: MeshLookup) {
  const active = new Map<OrganBusinessName, HighlightState>()

  function restoreMesh(organ: OrganBusinessName) {
    const state = active.get(organ)
    if (!state) return
    const original = state.mesh.userData.originalMaterial as THREE.Material | THREE.Material[] | undefined
    if (original) state.mesh.material = original
    state.mesh.userData.highlightLevel = null
    state.mesh.userData.pickable = true
    state.material.dispose()
    active.delete(organ)
  }

  function setHighlight(organ: OrganBusinessName, level: HumanBodyAlarmLevel | null) {
    if (!level) {
      restoreMesh(organ)
      return
    }
    const mesh = getMesh(organ)
    if (!mesh) return
    const current = active.get(organ)
    if (current?.level === level) return
    restoreMesh(organ)

    if (!mesh.userData.originalMaterial) {
      mesh.userData.originalMaterial = mesh.material
    }
    const material = cloneMaterial(level)
    mesh.material = material
    mesh.userData.highlightLevel = level
    mesh.userData.pickable = false
    active.set(organ, {
      mesh,
      level,
      material,
      phase: Math.random() * Math.PI * 2,
    })
  }

  function update(elapsedSeconds: number) {
    active.forEach((state) => {
      const config = ALARM_LEVELS[state.level]
      if (!config.blinkHz) return
      state.material.emissiveIntensity = 0.35 + 1.2 * Math.abs(Math.sin(Math.PI * 2 * config.blinkHz * elapsedSeconds + state.phase))
    })
  }

  function dispose() {
    active.forEach((state, organ) => {
      const original = state.mesh.userData.originalMaterial as THREE.Material | THREE.Material[] | undefined
      if (original) state.mesh.material = original
      disposeMaterial(state.material)
      state.mesh.userData.highlightLevel = null
      state.mesh.userData.pickable = true
      active.delete(organ)
    })
  }

  return {
    setHighlight,
    update,
    dispose,
  }
}
