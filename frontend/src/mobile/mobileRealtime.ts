import { alertIdOf, firstText, patientIdOf } from './mobileData'

export function alertBelongsToMobileScope(alert: any, deptCode?: string, deptLabel?: string) {
  const code = String(deptCode || '').trim()
  const dept = String(deptLabel || '').trim()
  if (!code && (!dept || dept === '全院')) return true

  const alertCode = firstText(alert, ['deptCode', 'dept_code', 'departmentCode'])
    || firstText(alert?.extra, ['deptCode', 'dept_code', 'departmentCode'])
  if (code && alertCode) return alertCode === code

  const alertDept = firstText(alert, ['dept', 'hisDept', 'department', 'deptName'])
    || firstText(alert?.extra, ['dept', 'hisDept', 'department', 'deptName'])
  if (dept && dept !== '全院' && alertDept) return alertDept === dept

  return true
}

export function alertMatchesPatient(alert: any, patient: any) {
  const alertPatientId = firstText(alert, ['patient_id', 'patientId'])
  const alertBed = firstText(alert, ['bed', 'hisBed', 'bed_no', 'bedNo'])
  const patientIds = [
    patientIdOf(patient),
    firstText(patient, ['_id', 'id']),
    firstText(patient, ['hisPid', 'patient_id', 'patientId']),
  ].filter(Boolean)
  const patientBeds = [
    firstText(patient, ['hisBed', 'bed', 'bed_no', 'bedNo']),
  ].filter(Boolean)
  return Boolean((alertPatientId && patientIds.includes(alertPatientId)) || (alertBed && patientBeds.includes(alertBed)))
}

export function mergeMobileAlert(rows: any[], alert: any, limit = 80) {
  if (!alert) return rows
  const id = alertIdOf(alert)
  const next = [...rows]
  const index = id ? next.findIndex((item) => alertIdOf(item) === id) : -1
  if (index >= 0) next.splice(index, 1, { ...next[index], ...alert })
  else next.unshift(alert)
  return next.slice(0, limit)
}
