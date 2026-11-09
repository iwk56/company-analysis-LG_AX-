// 숫자 표시 규칙 (docs/spec.md 0장 "숫자 표시 규칙"). 화면의 숫자는 모두 이 파일의 함수를 거친다.
// 저장값은 바꾸지 않는다: 금액은 원 단위 정수, 비율은 소수(0.123 = 12.3%).

export const MINUS = '−' // − (하이픈이 아닌 마이너스 기호)

export interface Formatted {
  text: string
  negative: boolean // true면 화면에서 빨간색
  muted: boolean // true면 회색 (해당 없음·자료 없음)
}

/** 백엔드 계산 결과의 비율 한 칸 */
export interface Metric {
  value: number | null
  na_reason: string | null
  year_end_only: boolean
}

export type MetricKind = 'percent' | 'multiple' | 'change' | 'pp'

const NO_DATA = '자료 없음'
const WON_PER_JO = 1e12
const WON_PER_EOK = 1e8
const CARD_MIN_JO = 0.1 // 이보다 작으면 "0.0조"로 보이므로 억 원으로 대신 표시
const YEAR_END_MARK = '†'

function usable(x: number | null | undefined): x is number {
  return typeof x === 'number' && Number.isFinite(x)
}

// 반올림은 0에서 먼 쪽으로 (−2.5 → −3). 1e-9는 2.4999999999처럼 저장된 값 보정용
function round(abs: number, digits: number): number {
  const factor = 10 ** digits
  return Math.round(abs * factor + 1e-9) / factor
}

function withComma(abs: number, digits: number): string {
  return abs.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })
}

// 부호는 반올림한 뒤에 정한다: −0.04조는 "0.0"이지 "−0.0"이 아니다
function build(x: number, digits: number, suffix: string, signed: boolean): Formatted {
  const rounded = round(Math.abs(x), digits)
  const negative = x < 0 && rounded !== 0
  const sign = negative ? MINUS : signed && rounded !== 0 ? '+' : ''
  return { text: `${sign}${withComma(rounded, digits)}${suffix}`, negative, muted: false }
}

export function noData(text: string = NO_DATA): Formatted {
  return { text, negative: false, muted: true }
}

/** 카드용 금액: 조 원, 소수 첫째 자리. 0.1조 원 미만이면 억 원 */
export function formatWonCard(won: number | null | undefined): Formatted {
  if (!usable(won)) return noData()
  const jo = won / WON_PER_JO
  if (Math.abs(jo) < CARD_MIN_JO) return build(won / WON_PER_EOK, 0, '억 원', false)
  return build(jo, 1, '조 원', false)
}

/** 증감·영향 금액 카드: +1.2조 원 / −350억 원 */
export function formatWonCardDelta(won: number | null | undefined): Formatted {
  if (!usable(won)) return noData()
  const jo = won / WON_PER_JO
  if (Math.abs(jo) < CARD_MIN_JO) return build(won / WON_PER_EOK, 0, '억 원', true)
  return build(jo, 1, '조 원', true)
}

/** 표용 금액: 억 원, 정수, 천 단위 쉼표. 단위는 표 제목에 쓰므로 숫자만 돌려준다 */
export function formatWonTable(won: number | null | undefined): Formatted {
  if (!usable(won)) return noData()
  return build(won / WON_PER_EOK, 0, '', false)
}

/** 표의 증감 금액: +1,234 / −567 (단위는 표 제목에 표시) */
export function formatWonTableDelta(won: number | null | undefined): Formatted {
  if (!usable(won)) return noData()
  return build(won / WON_PER_EOK, 0, '', true)
}

/** 평균 급여: 만 원 단위, 정수. 18,500만 원 */
export function formatWonMan(won: number | null | undefined): Formatted {
  if (!usable(won)) return noData()
  return build(won / 1e4, 0, '만 원', false)
}

/** 사람 수: 34,549명 */
export function formatPeople(n: number | null | undefined): Formatted {
  if (!usable(n)) return noData()
  return build(n, 0, '명', false)
}

/** 근속연수: 13.4년 */
export function formatYears(n: number | null | undefined): Formatted {
  if (!usable(n)) return noData()
  return build(n, 1, '년', false)
}

/** 비율: 28.9% */
export function formatPercent(ratio: number | null | undefined): Formatted {
  if (!usable(ratio)) return noData()
  return build(ratio * 100, 1, '%', false)
}

/** 주가: 원 단위 정수. 1,418,000원 */
export function formatPrice(won: number | null | undefined): Formatted {
  if (!usable(won)) return noData()
  return build(won, 0, '원', false)
}

/** 환율: 1,337.2원 (원/달러, 소수 첫째 자리) */
export function formatExchangeRate(won: number | null | undefined): Formatted {
  if (!usable(won)) return noData()
  return build(won, 1, '원', false)
}

/** 기준금리: 2.75% (0.25%p 단위로 움직이므로 소수 둘째 자리. 저장값은 이미 % 단위) */
export function formatBaseRate(percent: number | null | undefined): Formatted {
  if (!usable(percent)) return noData()
  return build(percent, 2, '%', false)
}

/** 증감률: +230.8% / −26.6% */
export function formatChange(ratio: number | null | undefined): Formatted {
  if (!usable(ratio)) return noData()
  return build(ratio * 100, 1, '%', true)
}

/** 비율끼리의 차이: +32.6%p / −5.0%p */
export function formatPercentPoint(ratioDiff: number | null | undefined): Formatted {
  if (!usable(ratioDiff)) return noData()
  return build(ratioDiff * 100, 1, '%p', true)
}

/** 회전율·이자보상배율·재무레버리지: 3.8배 */
export function formatMultiple(x: number | null | undefined): Formatted {
  if (!usable(x)) return noData()
  return build(x, 1, '배', false)
}

const BY_KIND: Record<MetricKind, (v: number) => Formatted> = {
  percent: formatPercent,
  multiple: formatMultiple,
  change: formatChange,
  pp: formatPercentPoint,
}

/**
 * 백엔드가 계산한 비율 한 칸을 표시용으로 바꾼다.
 * 값이 없으면 백엔드가 준 이유를 그대로 보여주고(예: "해당 없음(적자)"), 이유도 없으면 "자료 없음".
 * 평균 대신 기말 값으로 계산한 칸은 숫자 뒤에 †를 붙인다.
 */
export function formatMetric(metric: Metric | null | undefined, kind: MetricKind): Formatted {
  if (!metric) return noData()
  if (!usable(metric.value)) return noData(metric.na_reason || NO_DATA)
  const out = BY_KIND[kind](metric.value)
  return metric.year_end_only ? { ...out, text: out.text + YEAR_END_MARK } : out
}

/** 신호등: 색 이름과 글자를 함께 쓴다 (색만으로 구분하지 않음) */
export function signalView(level: string | null | undefined): { label: string; tone: 'good' | 'warn' | 'bad' } | null {
  if (level === '양호') return { label: '양호', tone: 'good' }
  if (level === '주의') return { label: '주의', tone: 'warn' }
  if (level === '위험') return { label: '위험', tone: 'bad' }
  return null
}
