import type { MobileNavKey, MobileRole } from './types'

export type MobileNavItem = {
  key: MobileNavKey
  label: string
  icon: string
  path: string
  roles?: MobileRole[]
}

export const mobileNavItems: MobileNavItem[] = [
  { key: 'home', label: '首页', icon: '⌂', path: '/m' },
  { key: 'patients', label: '患者', icon: '▦', path: '/m/patients' },
  { key: 'alerts', label: '告警', icon: '!', path: '/m/alerts' },
  { key: 'tasks', label: '任务', icon: '✓', path: '/m/tasks' },
  { key: 'me', label: '我的', icon: '•', path: '/m/me' },
]

export function normalizeMobileRole(role: unknown): MobileRole {
  const text = String(role || '').trim().toLowerCase()
  if (['doctor', 'attending', 'resident'].includes(text)) return 'doctor'
  if (['nurse', 'charge_nurse'].includes(text)) return 'nurse'
  if (['head_nurse'].includes(text)) return 'head_nurse'
  if (['director', 'chief'].includes(text)) return 'director'
  if (['respiratory', 'respiratory_therapist', 'rt'].includes(text)) return 'respiratory'
  if (['nutrition', 'dietitian'].includes(text)) return 'nutrition'
  if (['admin', 'administrator'].includes(text)) return 'admin'
  return 'unknown'
}

export function visibleMobileNavItems(role: MobileRole) {
  return mobileNavItems.filter((item) => !item.roles || item.roles.includes(role) || role === 'unknown')
}

export function mobileRouteForKey(key: MobileNavKey) {
  return mobileNavItems.find((item) => item.key === key)?.path || '/m'
}

