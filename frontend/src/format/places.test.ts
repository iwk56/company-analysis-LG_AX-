import { describe, expect, it } from 'vitest'
import { placeOf } from './places'

describe('placeOf', () => {
  it('저장된 "N페이지" 이름을 새 위치로 바꾸고 뒤 설명은 그대로 둔다', () => {
    expect(placeOf('calc:cashflow', '2페이지 현금흐름 패턴 (코드 계산)')).toEqual({ label: '부록 C 현금흐름 패턴 (코드 계산)', target: 'cashflow' })
    expect(placeOf('cashflow', '2페이지 현금흐름 패턴')).toEqual({ label: '부록 C 현금흐름 패턴', target: 'cashflow' })
    expect(placeOf('swot_weaknesses', '1페이지 SWOT 약점')).toEqual({ label: '3장 SWOT 약점', target: 'swot' })
    expect(placeOf('signals', '1페이지 핵심 지표 신호등').label).toBe('1장 핵심 지표 신호등')
    expect(placeOf('p3:sensitivity', '3페이지 경제 환경 민감도').label).toBe('부록 A 경제 환경 민감도')
  })
  it('공시 주제는 번호와 제목을 남긴다', () => {
    expect(placeOf('topic_2', '3페이지 공시 주제 2 (자기주식)')).toEqual({ label: '2장 공시 주제 2 (자기주식)', target: 'topics' })
    expect(placeOf('p3:topic3', '3페이지 공시 주제 3').label).toBe('2장 공시 주제 3')
  })
  it('원문 자료 키는 저장된 이름 그대로, 이동할 섹션 없음', () => {
    expect(placeOf('dart:business', '2025 사업보고서 · 사업의 내용')).toEqual({ label: '2025 사업보고서 · 사업의 내용', target: null })
    expect(placeOf('ecos:fx', '한국은행 ECOS · 원/달러 환율 (최근 1년)').target).toBeNull()
  })
})
