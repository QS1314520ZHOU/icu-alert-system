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
    requiredRoles: ['doctor', 'director', 'researcher'],
    description: '相似病例检索',
  },
  'ai-causal-inference': {
    defaultEnabled: false,
    requiredRoles: ['doctor', 'director', 'researcher'],
    description: '因果推断分析',
  },
  'ai-what-if': {
    defaultEnabled: false,
    requiredRoles: ['doctor', 'director'],
    description: 'What-if模拟',
  },
  'ai-disease-trajectory': {
    defaultEnabled: true,
    requiredRoles: ['doctor', 'nurse', 'director'],
    description: '疾病轨迹推演',
  },
  'ai-evidence': {
    defaultEnabled: true,
    requiredRoles: ['doctor', 'nurse', 'head_nurse', 'director'],
    description: '循证证据检索',
  },
  'ai-decision-assistants': {
    defaultEnabled: false,
    requiredRoles: ['doctor', 'director'],
    description: '专项决策助手（无真实API时默认关闭）',
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
 */
export function canAccessPatientModule(
  _moduleKey: string,
  moduleConfig?: { featureFlag?: string; requiredRoles?: string[] },
  userRole?: string
): boolean {
  // Check feature flag
  if (moduleConfig?.featureFlag) {
    if (!isFeatureEnabled(moduleConfig.featureFlag)) {
      return false
    }
    // Also check flag-level role restriction
    const flagConfig = FEATURE_FLAGS[moduleConfig.featureFlag]
    if (flagConfig?.requiredRoles && flagConfig.requiredRoles.length > 0) {
      if (!userRole || !flagConfig.requiredRoles.includes(userRole.toLowerCase())) {
        return false
      }
    }
  }

  // Check module-level role restriction
  if (moduleConfig?.requiredRoles && moduleConfig.requiredRoles.length > 0) {
    if (!userRole || !moduleConfig.requiredRoles.includes(userRole.toLowerCase())) {
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
