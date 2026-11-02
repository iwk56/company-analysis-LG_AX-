import { describe, expect, it } from 'vitest'
import { paddedDomain } from './domain'

describe('paddedDomain', () => {
  const pad = { low: 0.2, high: 0.3 }
  it('모든 값을 포함하고 양쪽에 여유를 둔다', () => {
    const [lo, hi] = paddedDomain([-5, 10, 48.6], pad)
    expect(lo).toBeLessThan(-5)
    expect(hi).toBeGreaterThan(48.6)
    expect(48.6 - hi).toBeLessThan(-10) // 위쪽 이름표 자리
  })
  it('값이 한 곳에 몰려도 범위가 생긴다', () => {
    const [lo, hi] = paddedDomain([12, 12], pad)
    expect(hi - lo).toBeGreaterThan(0)
    expect(lo).toBeLessThan(12)
    expect(hi).toBeGreaterThan(12)
  })
})
