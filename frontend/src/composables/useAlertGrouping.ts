import { computed, ref, type Ref } from 'vue'

const WINDOW_MS = 4 * 3600 * 1000   // 4h 聚合窗
const NO_GROUP = new Set(['composite_deterioration', 'ai_risk', 'alert_reasoning'])

export type AlertGroup = {
  key: string
  latest: any
  count: number
  history: any[]
  firstAt: string
  openCount: number
}

export function useAlertGrouping(alerts: Ref<any[]>, focusedTypes?: Ref<string[] | undefined>) {
  const expanded = ref<Set<string>>(new Set())
  const ts = (v: any) => new Date(v || 0).getTime()

  const groupedAlerts = computed<AlertGroup[]>(() => {
    const buckets = new Map<string, AlertGroup>()
    for (const a of alerts.value || []) {
      const type = String(a?.alert_type || a?.rule_id || a?.name || 'unknown')
      const solo = NO_GROUP.has(type)
      const ackState = a?.acknowledged_at ? 'ack' : 'open'
      const win = Math.floor(ts(a?.created_at) / WINDOW_MS)
      const key = solo
        ? `solo__${a?._id || ts(a?.created_at)}`
        : `${type}__${ackState}__${win}`

      const g = buckets.get(key)
      if (!g) {
        buckets.set(key, {
          key, latest: a, count: 1, history: [a],
          firstAt: a?.created_at, openCount: ackState === 'open' ? 1 : 0,
        })
        continue
      }
      g.count++
      g.history.push(a)
      if (ackState === 'open') g.openCount++
      if (ts(a?.created_at) > ts(g.latest?.created_at)) g.latest = a
      if (ts(a?.created_at) < ts(g.firstAt)) g.firstAt = a?.created_at
    }
    const list = [...buckets.values()]
    list.forEach((g) => g.history.sort((x, y) => ts(y?.created_at) - ts(x?.created_at)))
    return list.sort((x, y) => ts(y.latest?.created_at) - ts(x.latest?.created_at))
  })

  const autoExpanded = computed(() => {
    const set = new Set(expanded.value)
    const focus = focusedTypes?.value
    if (focus?.length) {
      for (const g of groupedAlerts.value) {
        if (focus.includes(String(g.latest?.alert_type || ''))) set.add(g.key)
      }
    }
    return set
  })

  const isOpen = (key: string) => autoExpanded.value.has(key)
  const toggle = (key: string) => {
    const s = new Set(expanded.value)
    s.has(key) ? s.delete(key) : s.add(key)
    expanded.value = s
  }
  const expandFor = (alert: any) => {
    const hit = groupedAlerts.value.find((g) => g.history.some((h) => h?._id === alert?._id))
    if (hit) expanded.value = new Set(expanded.value).add(hit.key)
    return hit?.key
  }

  return { groupedAlerts, isOpen, toggle, expandFor }
}