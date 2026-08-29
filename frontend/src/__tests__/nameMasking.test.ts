import { describe, it, expect } from 'vitest'

/**
 * Patient Name Masking Tests
 *
 * Verifies that patient names are properly desensitized.
 */

function maskName(name: string): string {
  if (!name || name.length <= 1) return name || '未知'
  if (name.length === 2) return name[0] + '*'
  return name[0] + '*'.repeat(name.length - 2) + name[name.length - 1]
}

describe('Patient Name Masking', () => {
  it('masks 2-char name', () => {
    expect(maskName('张三')).toBe('张*')
  })

  it('masks 3-char name', () => {
    expect(maskName('张三丰')).toBe('张*丰')
  })

  it('masks 4-char name', () => {
    expect(maskName('欧阳锋')).toBe('欧*锋') // 3 chars
    expect(maskName('司马相如')).toBe('司**如')
  })

  it('handles single char name', () => {
    expect(maskName('张')).toBe('张')
  })

  it('handles empty string', () => {
    expect(maskName('')).toBe('未知')
  })

  it('handles null/undefined', () => {
    expect(maskName(null as any)).toBe('未知')
    expect(maskName(undefined as any)).toBe('未知')
  })

  it('does not expose full name', () => {
    const fullName = '张三丰'
    const masked = maskName(fullName)
    expect(masked).not.toBe(fullName)
    expect(masked.length).toBe(fullName.length)
    // First char is preserved
    expect(masked[0]).toBe('张')
    // Last char is preserved for names > 2 chars
    expect(masked[masked.length - 1]).toBe('丰')
    // Middle is masked
    expect(masked[1]).toBe('*')
  })

  it('long name is properly masked', () => {
    const name = '欧阳娜娜'
    const masked = maskName(name)
    expect(masked[0]).toBe('欧')
    expect(masked[masked.length - 1]).toBe('娜')
    expect(masked).not.toContain(name.substring(1, name.length - 1))
  })
})
