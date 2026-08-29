/**
 * SmartCare AI — 风险等级颜色映射
 * 全系统风险等级统一视觉表达。
 */

export type RiskLevel = 'critical' | 'high' | 'medium' | 'low' | 'stable' | 'unknown'

export interface RiskVisual {
  color: string
  bgColor: string
  borderColor: string
  railCss: string
  label: string
  icon: string
  severity: number
}

export const RISK_MAP: Record<RiskLevel, RiskVisual> = {
  critical: { color: '#D92D20', bgColor: '#FEECEB', borderColor: '#FDA29B', railCss: '4px solid #D92D20', label: '危急',   icon: 'CloseCircleFilled',      severity: 5 },
  high:     { color: '#F79009', bgColor: '#FFF3E0', borderColor: '#FEC84B', railCss: '4px solid #F79009', label: '高风险', icon: 'ExclamationCircleFilled', severity: 4 },
  medium:   { color: '#E5B700', bgColor: '#FFF9D8', borderColor: '#FFE58F', railCss: '4px solid #E5B700', label: '中风险', icon: 'WarningFilled',           severity: 3 },
  low:      { color: '#12A66A', bgColor: '#E8F7F0', borderColor: '#84E1BC', railCss: '4px solid #12A66A', label: '低风险', icon: 'CheckCircleFilled',       severity: 2 },
  stable:   { color: '#12A66A', bgColor: '#E8F7F0', borderColor: '#84E1BC', railCss: '4px solid #12A66A', label: '稳定',   icon: 'CheckCircleFilled',       severity: 1 },
  unknown:  { color: '#98A2B3', bgColor: '#F2F4F7', borderColor: '#D0D5DD', railCss: '4px solid #98A2B3', label: '未知',   icon: 'QuestionCircleFilled',    severity: 0 },
}

export function getRiskLevel(score: number): RiskLevel {
  if (score >= 80) return 'critical'
  if (score >= 60) return 'high'
  if (score >= 40) return 'medium'
  if (score >= 20) return 'low'
  return 'stable'
}

export function getRiskVisual(level: RiskLevel): RiskVisual {
  return RISK_MAP[level] ?? RISK_MAP.unknown
}
