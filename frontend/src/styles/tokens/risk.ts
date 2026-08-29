/**
 * ICU Clinical Intelligence — 风险等级颜色映射
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
  critical: { color: '#991B1B', bgColor: '#FEF2F2', borderColor: '#FCA5A5', railCss: '4px solid #991B1B', label: '危急',   icon: 'CloseCircleFilled',      severity: 5 },
  high:     { color: '#DC2626', bgColor: '#FEF2F2', borderColor: '#FECACA', railCss: '4px solid #DC2626', label: '高风险', icon: 'ExclamationCircleFilled', severity: 4 },
  medium:   { color: '#F59E0B', bgColor: '#FFFBEB', borderColor: '#FDE68A', railCss: '4px solid #F59E0B', label: '中风险', icon: 'WarningFilled',           severity: 3 },
  low:      { color: '#16A34A', bgColor: '#F0FDF4', borderColor: '#BBF7D0', railCss: '4px solid #16A34A', label: '低风险', icon: 'CheckCircleFilled',       severity: 2 },
  stable:   { color: '#16A34A', bgColor: '#F0FDF4', borderColor: '#BBF7D0', railCss: '4px solid #16A34A', label: '稳定',   icon: 'CheckCircleFilled',       severity: 1 },
  unknown:  { color: '#94A3B8', bgColor: '#F1F5F9', borderColor: '#CBD5E1', railCss: '4px solid #94A3B8', label: '未知',   icon: 'QuestionCircleFilled',    severity: 0 },
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
