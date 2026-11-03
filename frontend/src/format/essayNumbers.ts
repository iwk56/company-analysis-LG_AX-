// 4장 "자기소개서에 쓸 숫자 모음" (spec.md 3장): 리포트에 저장된 계산 결과·검증된 추출값만 골라 정해진 틀의 한 줄 사실로 만든다.
// AI 호출 없음, 새 계산 없음. 값이 없거나 해당 없음·시세 없음·확인 불가인 항목은 줄을 넣지 않고 제외 이유를 남긴다.
import type { Enrichment, ReportDetail, SegmentsContent, RndContent } from '../api'
import type { Formatted, Metric } from './number'
import { formatMetric, formatPercent, formatWonCard } from './number'

export interface EssayLine {
  key: string
  lead: string // 값 앞 문장 ("2025년 매출액")
  value: Formatted // 숫자 표시 규칙 그대로 (음수는 빨강)
  tail: string // 값 뒤 문장 (" (AI 추출)" 등)
  basis: string | null // 연결/별도 (시가총액은 null)
  source: { label: string; url: string } | null
}
export interface EssayNumbers {
  lines: EssayLine[]
  excluded: { label: string; reason: string }[]
}

export const STOCK_SOURCE_URL = 'https://www.data.go.kr/data/15094808/openapi.do'
const NO_DATA = '자료 없음'

/** "2026.01~06" → "2026년 1~6월" (모양이 다르면 그대로) */
export function periodText(period: string): string {
  const m = /^(\d{4})\.(\d{1,2})~(\d{1,2})$/.exec(period.trim())
  return m ? `${m[1]}년 ${Number(m[2])}~${Number(m[3])}월` : period
}

/** 성공한 추출만 값으로 쓴다. 없으면 '자료 없음', 실패·원문 대조 실패(empty)면 '확인 불가' */
function extracted<T>(row: Enrichment<T> | undefined): { content: T | null; reason: string } {
  if (!row) return { content: null, reason: NO_DATA }
  if (row.status !== 'ok' || !row.content) return { content: null, reason: '확인 불가' }
  return { content: row.content, reason: NO_DATA }
}

export function essayNumbers(r: ReportDetail): EssayNumbers {
  const y = r.base_year
  const fy = r.financial_years.find((f) => f.year === y)
  const ratios = r.results.ratios[String(y)] ?? {}
  const annual = r.sources.find((s) => s.kind === 'annual_report' && s.year === y)
  const annualSrc = annual ? { label: annual.label, url: annual.url } : null
  const lines: EssayLine[] = []
  const excluded: EssayNumbers['excluded'] = []

  /** 값이 있으면 줄로, 없으면(회색 표시 = 자료 없음·해당 없음) 제외 목록으로 */
  const add = (key: string, label: string, value: Formatted, line: Omit<EssayLine, 'key' | 'value'>, reason?: string) => {
    if (value.muted) excluded.push({ label, reason: reason ?? value.text })
    else lines.push({ key, value, ...line })
  }
  const amount = (field: string) => {
    const v = fy?.[field]
    return typeof v === 'number' ? v : null
  }
  const metric = (key: string): Metric | undefined => ratios[key]
  const yearLine = (lead: string) => ({ lead: `${y}년 ${lead}`, tail: '', basis: r.basis, source: annualSrc })

  add('revenue', '매출액', formatWonCard(amount('revenue')), yearLine('매출액'))
  add('revenue_growth', '매출 성장률', formatMetric(metric('revenue_growth'), 'change'), yearLine('매출액 전년 대비'))
  add('operating_margin', '영업이익률', formatMetric(metric('operating_margin'), 'percent'), yearLine('영업이익률'))

  const rr = r.recent_results
  const interim = r.sources.find((s) => s.kind === 'interim_report')
  if (!rr) excluded.push({ label: '최근 실적', reason: '반기·3분기 보고서 없음' })
  else {
    add('recent', '최근 실적', formatMetric(r.results.recent_changes?.changes.operating_income, 'change'), {
      lead: `${periodText(rr.period_current)} 누적 영업이익 전년 같은 기간 대비`, tail: '', basis: rr.basis,
      source: interim ? { label: interim.label, url: interim.url } : null,
    })
  }

  add('debt_ratio', '부채비율', formatMetric(metric('debt_ratio'), 'percent'), yearLine('부채비율'))
  add('cfo', '영업현금흐름', formatWonCard(amount('cfo')), yearLine('영업현금흐름'))

  const seg = extracted<SegmentsContent>(r.enrichments.extract_segments)
  add('overseas_share', '해외 매출 비중', seg.content ? formatPercent(seg.content.overseas_share) : formatPercent(null),
    { lead: `${seg.content?.year ?? y}년 해외 매출 비중`, tail: ' (AI 추출)', basis: r.basis, source: annualSrc }, seg.content ? undefined : seg.reason)

  const rnd = extracted<RndContent>(r.enrichments.extract_rnd)
  add('rnd_ratio', '연구개발비 비중', formatPercent(rnd.content?.ratio_to_revenue),
    { lead: `${y}년 매출 대비 연구개발비`, tail: ' (연구개발비 AI 추출)', basis: r.basis, source: annualSrc }, rnd.content ? undefined : rnd.reason)

  const comp = r.results.comparison
  const target = comp?.rows.find((row) => row.is_target)
  const cap = target?.values.market_cap
  if (!comp) excluded.push({ label: '시가총액 순위', reason: '경쟁사 없음' })
  else if (!cap || cap.rank === null) excluded.push({ label: '시가총액 순위', reason: '시세 없음' })
  else {
    const asOf = target?.market_as_of ?? null
    lines.push({
      key: 'market_cap_rank', lead: `비교 기업 ${comp.ranked_counts.market_cap}곳 중 시가총액`,
      value: { text: `${cap.rank}위`, negative: false, muted: false },
      tail: ` (${asOf ? `${asOf} 기준, ` : ''}보통주 기준)`, basis: null,
      source: { label: `공공데이터포털 주식시세${asOf ? ` (기준일 ${asOf})` : ''}`, url: STOCK_SOURCE_URL },
    })
  }
  return { lines, excluded }
}
