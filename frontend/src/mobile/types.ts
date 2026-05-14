export type MobileRole =
  | 'doctor'
  | 'nurse'
  | 'head_nurse'
  | 'director'
  | 'respiratory'
  | 'nutrition'
  | 'admin'
  | 'unknown'

export type MobileNavKey = 'home' | 'patients' | 'alerts' | 'tasks' | 'consult' | 'me'

export type MobileActionSource = 'mobile_h5'

export const MOBILE_ACTION_SOURCE: MobileActionSource = 'mobile_h5'

