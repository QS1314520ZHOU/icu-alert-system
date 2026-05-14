import type { OrganBusinessName, OrganMapEntry } from '../../../types/organ'

export const ORGAN_MAP: Record<OrganBusinessName, OrganMapEntry> = {
  heart: { mesh: 'Cor', svg: '#svg-heart', label: '心脏' },
  left_lung: { mesh: 'Pulmo_sinister', svg: '#svg-l-lung', label: '左肺' },
  right_lung: { mesh: 'Pulmo_dexter', svg: '#svg-r-lung', label: '右肺' },
  liver: { mesh: 'Hepar', svg: '#svg-liver', label: '肝脏' },
  left_kidney: { mesh: 'Ren_sinister', svg: '#svg-l-kidney', label: '左肾' },
  right_kidney: { mesh: 'Ren_dexter', svg: '#svg-r-kidney', label: '右肾' },
  brain: { mesh: 'Cerebrum', svg: '#svg-brain', label: '脑' },
  stomach: { mesh: 'Gaster', svg: '#svg-stomach', label: '胃' },
  intestine: { mesh: 'Intestinum', svg: '#svg-intestine', label: '肠' },
  spleen: { mesh: 'Lien', svg: '#svg-spleen', label: '脾脏' },
  pancreas: { mesh: 'Pancreas', svg: '#svg-pancreas', label: '胰腺' },
  bladder: { mesh: 'Vesica_urinaria', svg: '#svg-bladder', label: '膀胱' },
}

const meshLookup = new Map<string, OrganBusinessName>()
const svgLookup = new Map<string, OrganBusinessName>()

for (const [businessName, entry] of Object.entries(ORGAN_MAP) as Array<[OrganBusinessName, OrganMapEntry]>) {
  meshLookup.set(entry.mesh.toLowerCase(), businessName)
  svgLookup.set(entry.svg.replace(/^#/, '').toLowerCase(), businessName)
}

export function meshToBusinessName(meshName: string): OrganBusinessName | null {
  return meshLookup.get(String(meshName || '').trim().toLowerCase()) || null
}

export function svgToBusinessName(svgId: string): OrganBusinessName | null {
  return svgLookup.get(String(svgId || '').trim().replace(/^#/, '').toLowerCase()) || null
}

export function organLabel(organ: string): string {
  return ORGAN_MAP[organ as OrganBusinessName]?.label || organ
}

export function organMeshName(organ: string): string {
  return ORGAN_MAP[organ as OrganBusinessName]?.mesh || ''
}

export function organSvgSelector(organ: string): string {
  return ORGAN_MAP[organ as OrganBusinessName]?.svg || ''
}

export function isKnownOrgan(value: string): value is OrganBusinessName {
  return Boolean(ORGAN_MAP[value as OrganBusinessName])
}
