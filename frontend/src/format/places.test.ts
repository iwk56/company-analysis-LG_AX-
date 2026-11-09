import { describe, expect, it } from 'vitest'
import { placeOf } from './places'

describe('placeOf', () => {
  it('저장된 옛 위치(N페이지·N장·부록)를 떼고 탭 이름을 붙인다', () => {
    expect(placeOf('calc:cashflow', '2페이지 현금흐름 패턴 (코드 계산)')).toEqual({ label: '현금흐름 탭 · 현금흐름 패턴 (코드 계산)', target: 'cashflow' })
    expect(placeOf('swot_weaknesses', '1페이지 SWOT 약점')).toEqual({ label: '전망·리스크 탭 · SWOT 약점', target: 'swot' })
    expect(placeOf('signals', '1페이지 핵심 지표 신호등').label).toBe('한눈에 탭 · 핵심 지표 신호등')
    expect(placeOf('p3:sensitivity', '3페이지 경제 환경 민감도').label).toBe('산업·경쟁 탭 · 경제 환경 민감도')
    expect(placeOf('pdf:position', '1장 업계 위치 (회사가 밝힌 내용)').label).toBe('산업·경쟁 탭 · 업계 위치 (회사가 밝힌 내용)')
    expect(placeOf('check:concentration', '4장 고객·제품 의존도 (코드 판정)').label).toBe('전망·리스크 탭 · 고객·제품 의존도 (코드 판정)')
  })
  it('공시 주제는 번호와 제목을 남긴다', () => {
    expect(placeOf('topic_2', '3페이지 공시 주제 2 (자기주식)')).toEqual({ label: '최근 이슈 탭 · 공시 주제 2 (자기주식)', target: 'topics' })
  })
  it('원문 자료 키는 저장된 이름 그대로, 이동할 섹션 없음', () => {
    expect(placeOf('dart:business', '2025 사업보고서 · 사업의 내용')).toEqual({ label: '2025 사업보고서 · 사업의 내용', target: null })
    expect(placeOf('ecos:fx', '한국은행 ECOS · 원/달러 환율 (최근 1년)').target).toBeNull()
  })
})
