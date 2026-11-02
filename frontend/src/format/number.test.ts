import { describe, expect, it } from 'vitest'
import {
  formatBaseRate,
  formatChange,
  formatExchangeRate,
  formatMetric,
  formatMultiple,
  formatPercent,
  formatPercentPoint,
  formatWonCard,
  formatWonTable,
  signalView,
} from './number'

describe('formatWonCard (조 원, 소수 첫째 자리)', () => {
  it('SK하이닉스 2025 영업현금흐름', () => {
    expect(formatWonCard(53_373_126_000_000)).toEqual({ text: '53.4조 원', negative: false, muted: false })
  })
  it('음수는 − 기호와 빨간색 표시', () => {
    expect(formatWonCard(-1_444_992_000_000)).toEqual({ text: '−1.4조 원', negative: true, muted: false })
  })
  it('0.1조 원 미만은 0.0조로 보이지 않게 억 원으로 표시', () => {
    expect(formatWonCard(4_000_000_000)).toMatchObject({ text: '40억 원' })
    expect(formatWonCard(-35_000_000_000)).toMatchObject({ text: '−350억 원', negative: true })
  })
  it('경계값 0.1조 원은 조 원', () => {
    expect(formatWonCard(100_000_000_000).text).toBe('0.1조 원')
  })
  it('값이 없으면 자료 없음', () => {
    expect(formatWonCard(null)).toEqual({ text: '자료 없음', negative: false, muted: true })
    expect(formatWonCard(undefined).text).toBe('자료 없음')
    expect(formatWonCard(NaN).text).toBe('자료 없음')
  })
})

describe('formatWonTable (억 원, 쉼표, 숫자만)', () => {
  it('SK하이닉스 2025 매출액 97조 1,466억 7,500만 원 → 971,467', () => {
    expect(formatWonTable(97_146_675_000_000)).toEqual({ text: '971,467', negative: false, muted: false })
  })
  it('음수', () => {
    expect(formatWonTable(-7_730_313_000_000)).toEqual({ text: '−77,303', negative: true, muted: false })
  })
  it('0.5억은 0에서 먼 쪽으로 올림 (양수·음수 모두)', () => {
    expect(formatWonTable(150_000_000).text).toBe('2')
    expect(formatWonTable(-150_000_000).text).toBe('−2')
  })
  it('반올림해서 0이 되면 음수로 표시하지 않음', () => {
    expect(formatWonTable(-40_000_000)).toEqual({ text: '0', negative: false, muted: false })
    expect(formatWonTable(0).text).toBe('0')
  })
  it('값이 없으면 자료 없음', () => {
    expect(formatWonTable(null).text).toBe('자료 없음')
  })
})

describe('비율·증감·배수', () => {
  it('비율은 소수 첫째 자리 %', () => {
    expect(formatPercent(0.28862737881982403).text).toBe('28.9%')
    expect(formatPercent(0.5492022181066609).text).toBe('54.9%')
    expect(formatPercent(0).text).toBe('0.0%')
  })
  it('음수 비율', () => {
    expect(formatPercent(-0.23592685391704665)).toEqual({ text: '−23.6%', negative: true, muted: false })
  })
  it('증감률은 부호가 붙은 %', () => {
    expect(formatChange(2.308036551694231).text).toBe('+230.8%')
    expect(formatChange(-0.26569772267975883)).toEqual({ text: '−26.6%', negative: true, muted: false })
    expect(formatChange(0).text).toBe('0.0%')
  })
  it('비율 차이는 %p', () => {
    expect(formatPercentPoint(0.3264943567030315).text).toBe('+32.6%p')
    expect(formatPercentPoint(-0.05)).toMatchObject({ text: '−5.0%p', negative: true })
  })
  it('배수는 소수 첫째 자리 + 배', () => {
    expect(formatMultiple(3.77).text).toBe('3.8배')
    expect(formatMultiple(-1.2686855620402329)).toEqual({ text: '−1.3배', negative: true, muted: false })
  })
  it('천 단위 쉼표 (큰 비율)', () => {
    expect(formatPercent(12.3456).text).toBe('1,234.6%')
  })
})

describe('formatMetric (백엔드 계산 칸)', () => {
  it('값이 있으면 종류에 맞게 표시', () => {
    const m = { value: 0.1544846900124253, na_reason: null, year_end_only: false }
    expect(formatMetric(m, 'percent').text).toBe('15.4%')
    expect(formatMetric({ ...m, value: 1.8260165404456412 }, 'multiple').text).toBe('1.8배')
    expect(formatMetric({ ...m, value: 0.0326 }, 'pp').text).toBe('+3.3%p')
  })
  it('해당 없음은 백엔드가 준 이유와 함께, 회색으로', () => {
    const m = { value: null, na_reason: '해당 없음(적자)', year_end_only: false }
    expect(formatMetric(m, 'multiple')).toEqual({ text: '해당 없음(적자)', negative: false, muted: true })
  })
  it('값도 이유도 없으면 자료 없음', () => {
    expect(formatMetric({ value: null, na_reason: null, year_end_only: false }, 'percent').text).toBe('자료 없음')
    expect(formatMetric(undefined, 'percent').text).toBe('자료 없음')
  })
  it('평균 대신 기말 값으로 계산한 칸에는 †', () => {
    const m = { value: 0.1544846900124253, na_reason: null, year_end_only: true }
    expect(formatMetric(m, 'percent').text).toBe('15.4%†')
  })
  it('해당 없음에는 †를 붙이지 않음', () => {
    const m = { value: null, na_reason: '해당 없음(전기 자료 없음)', year_end_only: true }
    expect(formatMetric(m, 'change').text).toBe('해당 없음(전기 자료 없음)')
  })
})

describe('signalView', () => {
  it('색 이름과 글자를 함께 돌려준다', () => {
    expect(signalView('양호')).toEqual({ label: '양호', tone: 'good' })
    expect(signalView('주의')).toEqual({ label: '주의', tone: 'warn' })
    expect(signalView('위험')).toEqual({ label: '위험', tone: 'bad' })
  })
  it('판정이 없으면(첫 연도 등) null', () => {
    expect(signalView(null)).toBeNull()
    expect(signalView('알 수 없음')).toBeNull()
  })
})

describe('formatExchangeRate / formatBaseRate', () => {
  it('환율은 소수 첫째 자리에 쉼표와 "원"', () => {
    expect(formatExchangeRate(1337.2)).toEqual({ text: '1,337.2원', negative: false, muted: false })
    expect(formatExchangeRate(1427.45).text).toBe('1,427.5원')
  })
  it('기준금리는 소수 둘째 자리 (2.75%가 2.8%로 보이지 않게)', () => {
    expect(formatBaseRate(2.75).text).toBe('2.75%')
    expect(formatBaseRate(3).text).toBe('3.00%')
  })
  it('값이 없으면 자료 없음', () => {
    expect(formatExchangeRate(null)).toMatchObject({ text: '자료 없음', muted: true })
    expect(formatBaseRate(undefined)).toMatchObject({ text: '자료 없음', muted: true })
  })
})
