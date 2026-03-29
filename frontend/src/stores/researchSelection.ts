import { defineStore } from 'pinia'

export type CohortSnapshot = {
  id: string | null
  name: string
  type?: 'saved' | 'dept' | 'builder' | 'manual'
  patientCount: number
  department?: string | null
  deptCode?: string | null
}

export const useResearchSelectionStore = defineStore('researchSelection', {
  state: () => ({
    selectedVariables: [] as string[],
    variableSummaries: {} as Record<string, any>,
    selectedPatientIds: [] as string[],
    patientIdsVersion: 0,
    cohort: null as CohortSnapshot | null,
  }),
  getters: {
    selectedCount: (state) => state.selectedVariables.length,
  },
  actions: {
    initializeVariables(defaultFields: string[]) {
      if (!this.selectedVariables.length) {
        this.selectedVariables = Array.from(new Set(defaultFields))
      }
    },
    setSelectedVariables(fields: string[]) {
      this.selectedVariables = Array.from(new Set((fields || []).filter(Boolean)))
    },
    toggleVariable(field: string) {
      const token = String(field || '').trim()
      if (!token) return
      if (this.selectedVariables.includes(token)) {
        this.selectedVariables = this.selectedVariables.filter((item) => item !== token)
      } else {
        this.selectedVariables = [...this.selectedVariables, token]
      }
    },
    selectVariables(fields: string[]) {
      const merged = new Set([...this.selectedVariables, ...(fields || []).filter(Boolean)])
      this.selectedVariables = Array.from(merged)
    },
    clearSelectedVariables() {
      this.selectedVariables = []
    },
    setVariableSummaries(payload: Record<string, any>) {
      this.variableSummaries = { ...(payload || {}) }
    },
    setPatientIds(ids: string[]) {
      const normalized = Array.from(new Set((ids || []).map((id) => String(id || '').trim()).filter(Boolean)))
      this.selectedPatientIds = normalized
      this.patientIdsVersion += 1
    },
    setCohort(snapshot: CohortSnapshot | null) {
      this.cohort = snapshot
    },
  },
})
