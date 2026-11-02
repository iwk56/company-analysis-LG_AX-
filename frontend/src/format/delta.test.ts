import { describe, expect, it } from 'vitest'
import { direction, difference, relativeChange } from './delta'

describe('difference', () => {
  it('두 비율의 차이', () => {
    expect(difference(0.5, 0.4)).toBeCloseTo(0.1)
  })
  it('한쪽이 없으면 null', () => {
    expect(difference(null, 0.4)).toBeNull()
    expect(difference(0.5, undefined)).toBeNull()
  })
})

describe('relativeChange', () => {
  it('SK하이닉스 영업현금흐름 2025 vs 2024', () => {
    expect(relativeChange(53_373_126_000_000, 29_795_885_000_000)).toBeCloseTo(0.7913, 3)
  })
  it('전기가 음수이면 절댓값으로 나눈다', () => {
    expect(relativeChange(-50, -100)).toBeCloseTo(0.5)
  })
  it('전기가 0이거나 없으면 null', () => {
    expect(relativeChange(10, 0)).toBeNull()
    expect(relativeChange(10, null)).toBeNull()
  })
})

describe('direction', () => {
  it('부호에 따라 방향', () => {
    expect(direction(0.1)).toBe('up')
    expect(direction(-0.1)).toBe('down')
  })
  it('표시상 0.0이 되는 작은 변화는 flat', () => {
    expect(direction(0)).toBe('flat')
    expect(direction(0.0002)).toBe('flat')
  })
  it('없으면 null', () => {
    expect(direction(null)).toBeNull()
  })
})
