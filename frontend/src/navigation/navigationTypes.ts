/**
 * Navigation type definitions for the unified navigation system.
 */

/** Navigation mode determines which sidebar content to show */
export type NavigationMode = 'global' | 'patient' | 'embed'

/** A single navigation item (leaf node) */
export interface NavItem {
  key: string
  label: string
  icon: string
  path: string
  lines?: string[]
  /** If set, only users with one of these roles can see this item */
  requiredRoles?: string[]
  /** If set, this feature flag must be enabled for the item to show */
  featureFlag?: string
  /** Child items for expandable groups */
  children?: NavItem[]
}

/** A group of navigation items with a label */
export interface NavGroup {
  key: string
  label: string
  items: NavItem[]
  /** If set, only users with one of these roles can see this group */
  requiredRoles?: string[]
}

/** Result of navigation resolution */
export interface ResolvedNavigation {
  groups: NavGroup[]
  mode: NavigationMode
}

/** Options for the navigation resolver */
export interface NavigationResolveOptions {
  mode: NavigationMode
  role?: string
  permissions?: string[]
  featureFlags?: Record<string, boolean>
  activePatientId?: string
}
