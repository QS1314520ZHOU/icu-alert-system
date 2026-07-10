import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getTrajectoryPublicConfig } from '../api'

export type TrajectoryPublicConfig = {
  enabled: boolean
  horizon_hours: number
  default_codes: string[]
}

const DEFAULT_TRAJECTORY_CONFIG: TrajectoryPublicConfig = {
  enabled: true,
  horizon_hours: 6,
  default_codes: ['HR', 'MAP', 'SpO2', 'RR', 'Temp'],
}

export const useRuntimePublicConfigStore = defineStore('runtime-public-config', () => {
  const trajectory = ref<TrajectoryPublicConfig>({ ...DEFAULT_TRAJECTORY_CONFIG })
  const loaded = ref(false)
  const loading = ref(false)

  async function loadTrajectoryConfig(force = false) {
    if (loading.value) return trajectory.value
    if (loaded.value && !force) return trajectory.value
    loading.value = true
    try {
      const res = await getTrajectoryPublicConfig()
      const data = res.data || {}
      const horizon = Number(data.horizon_hours || DEFAULT_TRAJECTORY_CONFIG.horizon_hours)
      trajectory.value = {
        enabled: data.enabled !== false,
        horizon_hours: Math.max(1, Math.min(Number.isFinite(horizon) ? horizon : 6, 12)),
        default_codes: Array.isArray(data.default_codes) && data.default_codes.length
          ? data.default_codes.map((code: any) => String(code)).filter(Boolean)
          : [...DEFAULT_TRAJECTORY_CONFIG.default_codes],
      }
      loaded.value = true
    } catch {
      trajectory.value = { ...DEFAULT_TRAJECTORY_CONFIG }
      loaded.value = true
    } finally {
      loading.value = false
    }
    return trajectory.value
  }

  return { trajectory, loaded, loading, loadTrajectoryConfig }
})
