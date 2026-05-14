export type OrganBusinessName =
  | 'heart'
  | 'left_lung'
  | 'right_lung'
  | 'liver'
  | 'left_kidney'
  | 'right_kidney'
  | 'brain'
  | 'stomach'
  | 'intestine'
  | 'spleen'
  | 'pancreas'
  | 'bladder'

export type HumanBodyTier = 'high' | 'low' | 'fallback'
export type HumanBodyForceTier = 'high' | 'low' | '2d'

export type OrganMapEntry = {
  mesh: string
  svg: string
  label: string
}
