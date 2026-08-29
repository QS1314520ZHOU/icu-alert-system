/**
 * Navigation resolver — generates the final menu based on mode, role, and permissions.
 *
 * This is the SINGLE source of truth for what appears in the sidebar.
 * SideNav.vue calls this; it never builds menus directly.
 */
import type { NavigationMode, NavGroup, ResolvedNavigation, NavigationResolveOptions } from './navigationTypes'
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
 * Returns role-filtered navGroups from roleHomeConfig.
 */
function resolveGlobalNavigation(role?: string): ResolvedNavigation {
  const filteredGroups: NavGroup[] = globalNavGroups.map(group => {
    if (group.key === 'more') {
      // "更多" group items come from moreMenuItems
      return {
        key: group.key,
        label: group.label,
        items: moreMenuItems.map(item => ({
          key: item.key,
          label: item.label,
          icon: item.icon,
          path: item.path,
        })),
      }
    }
    return {
      key: group.key,
      label: group.label,
      items: group.items.map(item => ({
        key: item.key,
        label: item.label,
        icon: item.icon,
        path: item.path,
        lines: item.lines,
      })),
    }
  })

  return { groups: filteredGroups, mode: 'global' }
}

/**
 * Resolve patient navigation (patient detail pages).
 * Returns patient modules from registry, filtered by role and feature flags.
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

  // Add "患者智能分析" expandable group with AI sub-modules
  const aiModules = PATIENT_MODULES.filter(m => m.group === 'ai-analysis')
  const accessibleAiModules = aiModules.filter(mod =>
    canAccessPatientModule(mod.moduleKey, {
      featureFlag: mod.featureFlag,
      requiredRoles: mod.requiredRoles,
    }, role)
  )

  if (accessibleAiModules.length > 0) {
    groups.push({
      key: 'ai-intelligence',
      label: '患者智能分析',
      items: accessibleAiModules.map(mod => moduleToNavItem(mod)),
    })
  }

  return { groups, mode: 'patient' }
}

/**
 * Convert a PatientModule to a NavItem for the sidebar.
 */
function moduleToNavItem(mod: PatientModule) {
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
