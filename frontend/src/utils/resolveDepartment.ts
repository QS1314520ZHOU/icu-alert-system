/**
 * Department display resolver — single source of truth for department display.
 *
 * No page should implement its own fallback logic.
 */

export interface DepartmentDisplay {
  displayDept: string
  displayDeptCode: string
}

/**
 * Resolve the department to display.
 * Priority: patient's dept > context dept > auth dept.
 */
export function resolveDepartment(opts: {
  patientDept?: string
  patientDeptCode?: string
  contextDept?: string
  contextDeptCode?: string
  authDept?: string
  authDeptCode?: string
}): DepartmentDisplay {
  const displayDept = opts.patientDept || opts.contextDept || opts.authDept || ''
  const displayDeptCode = opts.patientDeptCode || opts.contextDeptCode || opts.authDeptCode || ''
  return { displayDept, displayDeptCode }
}
