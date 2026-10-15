/**
 * Navigation resolver — generates the final menu based on mode, role, and permissions.
 *
 * This is the SINGLE source of truth for what appears in the sidebar.
 * SideNav.vue calls this; it never builds menus directly.
 */
import type { NavGroup, NavItem, ResolvedNavigation, NavigationResolveOptions } from './navigationTypes'
import { navGroups as globalNavGroups, moreMenuItems } from '../config/roleHomeConfig'
import { PATIENT_MODULES, MODULE_GROUPS, type PatientModule } from '../config/patientModuleRegistry'
import { canAccessPatientModule } from '../config/featureFlags'

/**
 * Resolve the navigation for the current context.
 */
export function resolveNavigation(opts: NavigationResolveOptions): ResolvedNavigation {
  const { mode, role } = opts

  if (mode === 'embed') {
    return { groups: [], mode }
  }

  if (mode === 'patient') {
    return resolvePatientNavigation(role)
  }

  // Default: global mode
  return resolveGlobalNavigation(role)
}

/**
 * Resolve global navigation (non-patient pages).
 * Returns role-filtered navGroups from roleHomeConfig,
 * plus patient AI-analysis modules appended to the "AI 助手" group.
 */
function resolveGlobalNavigation(role?: string): ResolvedNavigation {
  const filteredGroups: NavGroup[] = globalNavGroups
    .filter(g => g.key !== 'more')
    .map(group => ({
      key: group.key,
      label: group.label,
      items: group.items.map(item => ({
        key: item.key,
        label: item.label,
        icon: item.icon,
        path: item.path,
        lines: item.lines,
      })),
    }))

  // Add "患者智能分析" group with AI modules from patientModuleRegistry
  const aiModules = PATIENT_MODULES.filter(m => m.group === 'ai-analysis')
  const accessibleAiModules = aiModules.filter(mod =>
    canAccessPatientModule(mod.moduleKey, {
      featureFlag: mod.featureFlag,
      requiredRoles: mod.requiredRoles,
    }, role)
  )

  if (accessibleAiModules.length > 0) {
    const aiItems = accessibleAiModules.map(mod => moduleToNavItem(mod))
    const aiGroup = filteredGroups.find(g => g.key === 'ai')
    if (aiGroup) {
      // "AI 助手"组已存在（roleHomeConfig）：追加患者智能分析模块
      aiGroup.items.push(...aiItems)
    } else {
      // 兜底：无 AI 组时在"患者"组后插入
      const patientGroupIndex = filteredGroups.findIndex(g => g.key === 'patients')
      const newAiGroup: NavGroup = {
        key: 'ai',
        label: 'AI 助手',
        items: aiItems,
      }
      if (patientGroupIndex >= 0) {
        filteredGroups.splice(patientGroupIndex + 1, 0, newAiGroup)
      } else {
        filteredGroups.push(newAiGroup)
      }
    }
  }

  // Add "更多" group at the end
  filteredGroups.push({
    key: 'more',
    label: '更多',
    items: moreMenuItems.map(item => ({
      key: item.key,
      label: item.label,
      icon: item.icon,
      path: item.path,
    })),
  })

  return { groups: filteredGroups, mode: 'global' }
}

/**
 * Resolve patient navigation (patient detail pages).
 * Returns patient modules from registry, filtered by role and feature flags.
 *
 * NOTE: MODULE_GROUPS already includes the 'ai-analysis' group — we iterate
 * once through MODULE_GROUPS to avoid duplicate AI entries.
 */
function resolvePatientNavigation(role?: string): ResolvedNavigation {
  const groups: NavGroup[] = []

  for (const group of MODULE_GROUPS) {
    const accessibleItems = group.modules
      .filter(mod => canAccessPatientModule(mod.moduleKey, {
        featureFlag: mod.featureFlag,
        requiredRoles: mod.requiredRoles,
      }, role))
      .map(mod => moduleToNavItem(mod))

    if (accessibleItems.length > 0) {
      groups.push({
        key: group.key,
        label: group.label,
        items: accessibleItems,
      })
    }
  }

  return { groups, mode: 'patient' }
}

/**
 * Convert a PatientModule to a NavItem for the sidebar.
 */
function moduleToNavItem(mod: PatientModule): NavItem {
  return {
    key: mod.moduleKey,
    label: mod.title,
    icon: mod.icon,
    path: mod.route || `/tool/${mod.moduleKey}`,
    requiredRoles: mod.requiredRoles,
    featureFlag: mod.featureFlag,
  }
}

/**
 * Get all accessible module keys for the current role.
 * Used by route guards and permission checks.
 */
export function getAccessibleModuleKeys(role?: string): string[] {
  return PATIENT_MODULES
    .filter(mod => canAccessPatientModule(mod.moduleKey, {
      featureFlag: mod.featureFlag,
      requiredRoles: mod.requiredRoles,
    }, role))
    .map(mod => mod.moduleKey)
}
