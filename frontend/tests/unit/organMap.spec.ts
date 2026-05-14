import { describe, expect, it } from 'vitest'
import { ORGAN_MAP, isKnownOrgan, meshToBusinessName, organLabel, organMeshName, organSvgSelector, svgToBusinessName } from '../../src/components/HumanBody/constants/organMap'

describe('ORGAN_MAP', () => {
  it('covers at least 12 ICU organs', () => {
    expect(Object.keys(ORGAN_MAP)).toHaveLength(12)
  })

  it('maps business names to mesh/svg/Chinese labels', () => {
    expect(ORGAN_MAP.heart.mesh).toBe('Cor')
    expect(ORGAN_MAP.left_lung.svg).toBe('#svg-l-lung')
    expect(organLabel('right_kidney')).toBe('右肾')
    expect(organMeshName('liver')).toBe('Hepar')
    expect(organSvgSelector('brain')).toBe('#svg-brain')
  })

  it('supports reverse mesh and svg lookup', () => {
    expect(meshToBusinessName('Pulmo_sinister')).toBe('left_lung')
    expect(meshToBusinessName('pulmo_dexter')).toBe('right_lung')
    expect(svgToBusinessName('#svg-pancreas')).toBe('pancreas')
    expect(svgToBusinessName('svg-bladder')).toBe('bladder')
  })

  it('returns null or false for unknown organs', () => {
    expect(meshToBusinessName('unknown')).toBeNull()
    expect(svgToBusinessName('#unknown')).toBeNull()
    expect(isKnownOrgan('unknown')).toBe(false)
  })
})
