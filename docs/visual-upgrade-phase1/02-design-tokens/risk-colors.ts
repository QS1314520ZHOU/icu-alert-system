/**
 * SmartCare AI — 风险等级颜色映射
 *
 * 统一全系统风险等级的视觉表达。
 * 所有风险状态必须同时提供：颜色 + 图标 + 文字标签。
 */

export type RiskLevel = 'critical' | 'high' | 'medium' | 'low' | 'stable' | 'unknown'

export interface RiskVisual {
  /** 主色 */
  color: string
  /** 背景色 */
  bgColor: string
  /** 边框色 */
  borderColor: string
  /** 左侧状态条 */
  railCss: string
  /** 中文标签 */
  label: string
  /** Ant Design图标名 */
  icon: string
  /** 优先级数值（用于排序） */
  severity: number
}

export const RISK_VISUAL_MAP: Record<RiskLevel, RiskVisual> = {
  critical: {
    color: '#D92D20',
    bgColor: '#FEECEB',
    borderColor: '#FDA29B',
    railCss: '4px solid #D92D20',
    label: '危急',
    icon: 'CloseCircleFilled',
    severity: 5,
  },
  high: {
    color: '#F79009',
    bgColor: '#FFF3E0',
    borderColor: '#FEC84B',
    railCss: '4px solid #F79009',
    label: '高风险',
    icon: 'ExclamationCircleFilled',
    severity: 4,
  },
  medium: {
    color: '#E5B700',
    bgColor: '#FFF9D8',
    borderColor: '#FFE58F',
    railCss: '4px solid #E5B700',
    label: '中风险',
    icon: 'WarningFilled',
    severity: 3,
  },
  low: {
    color: '#12A66A',
    bgColor: '#E8F7F0',
    borderColor: '#84E1BC',
    railCss: '4px solid #12A66A',
    label: '低风险',
    icon: 'CheckCircleFilled',
    severity: 2,
  },
  stable: {
    color: '#12A66A',
    bgColor: '#E8F7F0',
    borderColor: '#84E1BC',
    railCss: '4px solid #12A66A',
    label: '稳定',
    icon: 'CheckCircleFilled',
    severity: 1,
  },
  unknown: {
    color: '#98A2B3',
    bgColor: '#F2F4F7',
    borderColor: '#D0D5DD',
    railCss: '4px solid #98A2B3',
    label: '未知',
    icon: 'QuestionCircleFilled',
    severity: 0,
  },
}

/**
 * 根据风险分数获取风险等级
 * @param score 0-100的风险分数
 */
export function getRiskLevel(score: number): RiskLevel {
  if (score >= 80) return 'critical'
  if (score >= 60) return 'high'
  if (score >= 40) return 'medium'
  if (score >= 20) return 'low'
  return 'stable'
}

/**
 * 根据风险等级获取视觉配置
 */
export function getRiskVisual(level: RiskLevel): RiskVisual {
  return RISK_VISUAL_MAP[level] || RISK_VISUAL_MAP.unknown
}
