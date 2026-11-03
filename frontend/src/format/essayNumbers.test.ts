import { describe, expect, it } from 'vitest'
import type { ReportDetail } from '../api'
import { essayNumbers, periodText } from './essayNumbers'

const metric = (value: number | null, na_reason: string | null = null) => ({ value, na_reason, year_end_only: false })
const cell = (value: number | null, rank: number | null) => ({ value, na_reason: null, rank, vs_average: null })

function report(over: Partial<ReportDetail> = {}): ReportDetail {
  return {
    base_year: 2025,
    basis: '연결',
    financial_years: [{ year: 2025, revenue: 97.1e12, cfo: 50.2e12 }],
    results: {
      ratios: { 2025: { revenue_growth: metric(0.468), operating_margin: metric(0.486), debt_ratio: metric(0.352) } },
      recent_changes: { changes: { operating_income: metric(0.049) } },
      comparison: {
        ranked_counts: { market_cap: 3 },
        rows: [{ is_target: true, market_as_of: '2026-10-30', values: { market_cap: cell(1.03e15, 2) } }],
      },
    },
    recent_results: { period_current: '2026.01~06', basis: '연결' },
    sources: [
      { kind: 'annual_report', year: 2025, label: '2025 사업보고서 (연결재무제표)', rcept_no: '1', url: 'https://dart/a' },
      { kind: 'interim_report', year: 2026, label: '2026 반기보고서', rcept_no: '2', url: 'https://dart/i' },
    ],
    enrichments: {
      extract_segments: { status: 'ok', content: { year: 2025, products: [], overseas_share: 0.98 } },
      extract_rnd: { status: 'ok', content: { amount_won: 6.7e12, ratio_to_revenue: 0.069 } },
    },
    ...over,
  } as unknown as ReportDetail
}

const texts = (r: ReportDetail) => essayNumbers(r).lines.map((l) => `${l.lead} ${l.value.text}${l.tail}`)

describe('essayNumbers', () => {
  it('값이 모두 있으면 9줄을 정해진 순서와 틀로 만든다', () => {
    expect(texts(report())).toEqual([
      '2025년 매출액 97.1조 원',
      '2025년 매출액 전년 대비 +46.8%',
      '2025년 영업이익률 48.6%',
      '2026년 1~6월 누적 영업이익 전년 같은 기간 대비 +4.9%',
      '2025년 부채비율 35.2%',
      '2025년 영업현금흐름 50.2조 원',
      '2025년 해외 매출 비중 98.0% (AI 추출)',
      '2025년 매출 대비 연구개발비 6.9% (연구개발비 AI 추출)',
      '비교 기업 3곳 중 시가총액 2위 (2026-10-30 기준, 보통주 기준)',
    ])
    const out = essayNumbers(report())
    expect(out.excluded).toEqual([])
    expect(out.lines[0].source?.url).toBe('https://dart/a')
    expect(out.lines[3].source?.url).toBe('https://dart/i')
    expect(out.lines[8].source?.url).toContain('data.go.kr')
  })

  it('해당 없음·자료 없음은 줄을 빼고 이유를 남긴다', () => {
    const r = report()
    r.results.ratios['2025'].revenue_growth = metric(null, '전기 자료 없음')
    r.financial_years[0].revenue = null
    const out = essayNumbers(r)
    expect(out.lines.map((l) => l.key)).not.toContain('revenue_growth')
    expect(out.lines.map((l) => l.key)).not.toContain('revenue')
    expect(out.excluded).toEqual([{ label: '매출액', reason: '자료 없음' }, { label: '매출 성장률', reason: '전기 자료 없음' }])
  })

  it('영업현금흐름이 음수여도 줄을 넣고 음수로 표시한다', () => {
    const r = report()
    r.financial_years[0].cfo = -1.2e12
    const line = essayNumbers(r).lines.find((l) => l.key === 'cfo')
    expect(line?.value.negative).toBe(true)
  })

  it('시세가 없거나 경쟁사가 없으면 시가총액 순위를 뺀다', () => {
    const noStock = report()
    noStock.results.comparison!.rows[0].values.market_cap = cell(null, null)
    expect(essayNumbers(noStock).excluded).toEqual([{ label: '시가총액 순위', reason: '시세 없음' }])
    const old = report()
    old.results.comparison!.rows[0].values = {} // 5-B 이전 리포트: 시가총액 열 없음
    expect(essayNumbers(old).excluded).toEqual([{ label: '시가총액 순위', reason: '시세 없음' }])
    const none = report()
    delete none.results.comparison
    expect(essayNumbers(none).excluded).toEqual([{ label: '시가총액 순위', reason: '경쟁사 없음' }])
  })

  it('AI 추출을 원문과 대조하지 못했거나 아직 없으면 뺀다', () => {
    const r = report()
    r.enrichments = {
      extract_segments: { status: 'empty', content: null, message: '원문과 대조하지 못함' },
    } as unknown as ReportDetail['enrichments']
    const out = essayNumbers(r)
    expect(out.lines.map((l) => l.key)).not.toContain('overseas_share')
    expect(out.excluded).toEqual([{ label: '해외 매출 비중', reason: '확인 불가' }, { label: '연구개발비 비중', reason: '자료 없음' }])
  })

  it('반기·3분기 보고서가 없으면 최근 실적을 뺀다', () => {
    const out = essayNumbers(report({ recent_results: null, recent_reason: '아직 제출된 반기·3분기 보고서가 없습니다' }))
    expect(out.excluded).toEqual([{ label: '최근 실적', reason: '반기·3분기 보고서 없음' }])
  })

  it('별도 재무제표 리포트는 줄마다 별도 기준을 붙인다', () => {
    const out = essayNumbers(report({ basis: '별도' }))
    expect(out.lines.filter((l) => l.key !== 'recent' && l.key !== 'market_cap_rank').every((l) => l.basis === '별도')).toBe(true)
    expect(out.lines.find((l) => l.key === 'market_cap_rank')?.basis).toBeNull()
  })

  it('보고서 기간을 쉬운 말로 바꾼다', () => {
    expect(periodText('2026.01~09')).toBe('2026년 1~9월')
    expect(periodText('2026 상반기')).toBe('2026 상반기')
  })
})
