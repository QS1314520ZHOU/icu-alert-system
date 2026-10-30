/**
 * Feature flag configuration for patient AI modules.
 *
 * Each flag controls whether a module is accessible.
 * `defaultEnabled` controls production default.
 * `requiredRoles` optionally restricts to specific roles.
 */

export interface FeatureFlagConfig {
  defaultEnabled: boolean
  requiredRoles?: string[]
  description?: string
}

export const FEATURE_FLAGS: Record<string, FeatureFlagConfig> = {
  'ai-risk-prediction': {
    defaultEnabled: true,
    requiredRoles: ['doctor', 'nurse', 'head_nurse', 'director'],
    description: '风险预测模块',
  },
  'ai-integrated-risk': {
    defaultEnabled: true,
    requiredRoles: ['doctor', 'nurse', 'head_nurse', 'director'],
    description: '综合风险评估',
  },
  'ai-similar-cases': {
    defaultEnabled: true,
    requiredRoles: ['doctor', 'nurse', 'head_nurse', 'director', 'researcher'],
    description: '相似病例检索',
  },
  'ai-causal-inference': {
    defaultEnabled: true,
    requiredRoles: ['doctor', 'nurse', 'head_nurse', 'director', 'researcher'],
    description: '因果推断分析',
  },
  'ai-what-if': {
    defaultEnabled: true,
    requiredRoles: ['doctor', 'nurse', 'head_nurse', 'director'],
    description: 'What-if模拟',
  },
  'ai-disease-trajectory': {
    defaultEnabled: true,
    requiredRoles: ['doctor', 'nurse', 'head_nurse', 'director'],
    description: '疾病轨迹推演',
  },
  'ai-evidence': {
    defaultEnabled: true,
    requiredRoles: ['doctor', 'nurse', 'head_nurse', 'director'],
    description: '循证证据检索',
  },
  'ai-decision-assistants': {
    defaultEnabled: true,
    requiredRoles: ['doctor', 'director'],
    description: '专项决策助手（撤机/SBT、脓毒症集束，已接入真实接口）',
  },
  'ai-documents': {
    defaultEnabled: true,
    requiredRoles: ['doctor', 'nurse', 'head_nurse'],
    description: '文书与AI',
  },
  'ai-followup': {
    defaultEnabled: true,
    requiredRoles: ['doctor', 'nurse', 'head_nurse'],
    description: '随访管理',
  },
}

/**
 * Check if a feature flag is enabled.
 * In production, uses `defaultEnabled`. Can be overridden by runtime config.
 */
export function isFeatureEnabled(flag: string): boolean {
  const config = FEATURE_FLAGS[flag]
  if (!config) return false  // unknown flags default to disabled
  return config.defaultEnabled
}

/**
 * Check if the current user can access a patient module.
 *
 * Checks:
 * 1. Module's featureFlag is enabled
 * 2. User's role is in module's requiredRoles (if specified)
 * 3. User's role is in the feature flag's requiredRoles (if specified)
 *
 * NOTE: If userRole is not set (empty/undefined), we allow access.
 * This is for development/testing convenience and for systems without
 * strict role enforcement. In production, role should always be set.
 *
 * 模块角色权限开关（.env → VITE_ENABLE_MODULE_ROLE_GUARD）：
 * - 'true' 时按 requiredRoles 区分医生/护士等角色可见性（严格模式）
 * - 缺省/false（默认）时跳过所有 requiredRoles 检查，任何角色均可打开全部模块
 *   ——供不需要按角色控制模块权限的医院使用。
 * featureFlag（功能灰度）不受此开关影响，始终生效。
 */
export function isModuleRoleGuardEnabled(): boolean {
  return import.meta.env.VITE_ENABLE_MODULE_ROLE_GUARD === 'true'
}

export function canAccessPatientModule(
  _moduleKey: string,
  moduleConfig?: { featureFlag?: string; requiredRoles?: string[] },
  userRole?: string
): boolean {
  const roleGuard = isModuleRoleGuardEnabled()

  // Check feature flag
  if (moduleConfig?.featureFlag) {
    if (!isFeatureEnabled(moduleConfig.featureFlag)) {
      return false
    }
    // Also check flag-level role restriction
    if (roleGuard) {
      const flagConfig = FEATURE_FLAGS[moduleConfig.featureFlag]
      if (flagConfig?.requiredRoles && flagConfig.requiredRoles.length > 0) {
        // If role is not set, allow access (development mode / no role enforcement)
        if (userRole && !flagConfig.requiredRoles.includes(userRole.toLowerCase())) {
          return false
        }
      }
    }
  }

  // Check module-level role restriction
  if (roleGuard && moduleConfig?.requiredRoles && moduleConfig.requiredRoles.length > 0) {
    // If role is not set, allow access (development mode / no role enforcement)
    if (userRole && !moduleConfig.requiredRoles.includes(userRole.toLowerCase())) {
      return false
    }
  }

  return true
}

/**
 * Get a list of all feature flags for debugging/admin display.
 */
export function getAllFeatureFlags(): Array<{ flag: string } & FeatureFlagConfig> {
  return Object.entries(FEATURE_FLAGS).map(([flag, config]) => ({
    flag,
    ...config,
  }))
}
