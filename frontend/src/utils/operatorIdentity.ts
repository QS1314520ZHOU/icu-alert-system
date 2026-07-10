const OPERATOR_IDENTITY_KEY = 'icu_operator_identity'

export function getOperatorIdentity() {
  if (typeof window === 'undefined') return ''
  return String(window.localStorage.getItem(OPERATOR_IDENTITY_KEY) || '').trim()
}

export function setOperatorIdentity(value: string) {
  if (typeof window === 'undefined') return ''
  const normalized = String(value || '').trim()
  window.localStorage.setItem(OPERATOR_IDENTITY_KEY, normalized)
  return normalized
}

export function getOperatorIdentityLabel() {
  const value = getOperatorIdentity()
  return value || '未设置操作人'
}
