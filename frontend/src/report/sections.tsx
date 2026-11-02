import styles from '../app.module.css'
import type { FinancialYear, MetricMap, ReportDetail } from '../api'
import { ARROW, difference, direction, relativeChange } from '../format/delta'
import type { Direction } from '../format/delta'
import type { Formatted, MetricKind } from '../format/number'
import {
  formatChange, formatMetric, formatPercentPoint, formatWonCard, formatWonTable,
} from '../format/number'
import { dateText } from '../format/date'
import { Num, SignalBadge } from '../ui'
import { CashflowChart, LineGroupChart, TrendChart } from './charts'
import YearTable from './YearTable'

const EOK = 1e8
const yearsOf = (r: ReportDetail) => r.financial_years.map((y) => y.year).sort((a, b) => a - b)
const fyOf = (r: ReportDetail, year: number) => r.financial_years.find((y) => y.year === year)
const amount = (fy: FinancialYear | undefined, field: string): number | null => {
  const v = fy?.[field]
  return typeof v === 'number' ? v : null
}

// ───────────────────────── 상단 정보
export function Header({ r }: { r: ReportDetail }) {
  return (
    <section className={`${styles.card} ${styles.header}`}>
      <h1>{r.company.corp_name}</h1>
      <div className={styles.meta}>
        <span>업종 <b>{r.company.industry_name ?? '자료 없음'}</b></span>
        <span>생성일 <b>{dateText(r.created_at)}</b></span>
        <span>기준 사업연도 <b>{r.base_year}</b></span>
        <span>데이터 기준일 <b>{r.data_as_of}</b></span>
        <span>재무제표 <b>{r.basis}</b></span>
      </div>
      {r.year_count < 5 && <p className={styles.notice}>{r.year_count}년 자료만 있음 (상장 5년 미만이거나 수집된 연도가 적습니다)</p>}
      {[...r.warnings, ...r.notes].map((m) => <p key={m} className={styles.notice}>{m}</p>)}
    </section>
  )
}

// ───────────────────────── 1페이지: 핵심 지표 카드
function Card({ label, value, signal, reason, dir, deltaText }: {
  label: string
  value: Formatted
  signal: { level: string; reason: string } | null | undefined
  reason?: string
  dir: Direction | null
  deltaText: Formatted | null
}) {
  return (
    <div className={styles.metriccard}>
      <div className={styles.label}>{label}</div>
      <div className={styles.big}><Num f={value} /></div>
      <div className={styles.delta}>
        {dir && deltaText ? <>전년 대비 {ARROW[dir]} <Num f={deltaText} /></> : '전년 대비 비교 자료 없음'}
      </div>
      <div style={{ marginTop: 6 }}><SignalBadge level={signal?.level} reason={signal?.reason ?? reason} /></div>
      {signal && <div className={styles.why}>{signal.reason}</div>}
    </div>
  )
}

export function CoreCards({ r }: { r: ReportDetail }) {
  const y = String(r.base_year)
  const p = String(r.base_year - 1)
  const ratio = (year: string, key: string) => r.results.ratios[year]?.[key]
  const sig = (key: string) => r.results.signals[y]?.[key]
  const ppCard = (key: string, label: string, signalKey: string, main: (m: MetricMap[string]) => Formatted) => {
    const d = difference(ratio(y, key)?.value, ratio(p, key)?.value)
    return (
      <Card label={label} value={main(ratio(y, key))} signal={sig(signalKey)} dir={direction(d)}
        deltaText={d === null ? null : formatPercentPoint(d)} />
    )
  }
  const cfoDelta = relativeChange(amount(fyOf(r, r.base_year), 'cfo'), amount(fyOf(r, r.base_year - 1), 'cfo'))
  return (
    <div className={styles.cards}>
      {ppCard('revenue_growth', '매출 성장률', 'revenue_growth', (m) => formatMetric(m, 'change'))}
      {ppCard('operating_margin', '영업이익률', 'operating_margin', (m) => formatMetric(m, 'percent'))}
      {ppCard('debt_ratio', '부채비율', 'debt_ratio', (m) => formatMetric(m, 'percent'))}
      <Card label="영업현금흐름" value={formatWonCard(amount(fyOf(r, r.base_year), 'cfo'))} signal={sig('operating_cashflow')}
        dir={direction(cfoDelta)} deltaText={cfoDelta === null ? null : formatChange(cfoDelta)} />
    </div>
  )
}

// ───────────────────────── 2페이지: 최근 실적 박스
export function RecentBox({ r }: { r: ReportDetail }) {
  const rr = r.recent_results
  if (!rr) {
    return (
      <section className={styles.card}>
        <h3>최근 실적</h3>
        <p className={styles.muted}>{r.recent_reason ?? '아직 제출된 반기·3분기 보고서가 없습니다'}</p>
      </section>
    )
  }
  const ch = r.results.recent_changes
  const amountRow = (label: string, key: string, changeKey: string) => [
    label, formatWonTable(rr.current[key]), formatWonTable(rr.prior[key]), formatMetric(ch?.changes[changeKey], 'change' as MetricKind),
  ] as const
  const rows = [
    amountRow('매출액', 'revenue', 'revenue'),
    amountRow('영업이익', 'operating_income', 'operating_income'),
    ['영업이익률', formatMetric(ch?.operating_margin_current, 'percent'), formatMetric(ch?.operating_margin_prior, 'percent'),
      formatMetric(ch?.changes.operating_margin, 'pp')] as const,
    amountRow('지배주주 순이익', 'net_income_parent', 'net_income_parent'),
  ]
  const source = r.sources.find((s) => s.kind === 'interim_report')
  return (
    <section className={styles.card}>
      <h3>최근 실적 <span className={styles.unit}>{rr.year}년 {rr.report_name}보고서 · {rr.basis}재무제표 · 누적</span></h3>
      <p className={styles.tabletitle}>{rr.period_current} vs {rr.period_prior}<span className={styles.unit}>(단위: 억 원, 영업이익률은 %)</span></p>
      <table className={styles.table}>
        <thead><tr><th>항목</th><th>{rr.period_current}</th><th>{rr.period_prior}</th><th>증감</th></tr></thead>
        <tbody>
          {rows.map(([label, cur, prior, change]) => (
            <tr key={label}><td>{label}</td><td><Num f={cur} /></td><td><Num f={prior} /></td><td><Num f={change} /></td></tr>
          ))}
        </tbody>
      </table>
      {rr.notes.map((n) => <p key={n} className={styles.footnote}>{n}</p>)}
      {source && <p className={styles.footnote}>출처: <a href={source.url} target="_blank" rel="noreferrer">{source.label}</a></p>}
    </section>
  )
}

// ───────────────────────── 2페이지: 실적 추이 + 재무 수치 표
export function Trend({ r }: { r: ReportDetail }) {
  const years = yearsOf(r)
  const data = years.map((year) => ({
    year,
    revenue: (amount(fyOf(r, year), 'revenue') ?? NaN) / EOK,
    margin: (r.results.ratios[String(year)]?.operating_margin?.value ?? NaN) * 100,
  })).map((d) => ({ ...d, revenue: Number.isNaN(d.revenue) ? null : d.revenue, margin: Number.isNaN(d.margin) ? null : d.margin }))
  const row = (label: string, field: string) => ({ label, cells: years.map((y) => formatWonTable(amount(fyOf(r, y), field))) })
  return (
    <section className={styles.card}>
      <h3>실적 추이</h3>
      <TrendChart data={data} />
      <YearTable title="재무 수치" unit="억 원" years={years}
        rows={[row('매출액', 'revenue'), row('영업이익', 'operating_income'), row('당기순이익', 'net_income'),
          row('지배주주 순이익', 'net_income_parent'), row('자산총계', 'total_assets'), row('부채총계', 'total_liabilities'),
          row('자본총계', 'total_equity')]} />
    </section>
  )
}

// ───────────────────────── 2페이지: 재무비율 (그룹별 표 + 선 차트)
interface MetricDef { key: string; label: string; kind: MetricKind; chart: boolean }
const GROUPS: { name: string; unit: '%' | 'x'; metrics: MetricDef[]; chartNote?: string }[] = [
  { name: '수익성', unit: '%', metrics: [
    { key: 'operating_margin', label: '영업이익률', kind: 'percent', chart: true },
    { key: 'net_margin', label: '순이익률', kind: 'percent', chart: true },
    { key: 'roe', label: 'ROE', kind: 'percent', chart: true },
    { key: 'roa', label: 'ROA', kind: 'percent', chart: true }] },
  { name: '안정성', unit: '%', chartNote: '이자보상배율은 단위(배)가 달라 표에서만 보여줍니다', metrics: [
    { key: 'debt_ratio', label: '부채비율', kind: 'percent', chart: true },
    { key: 'current_ratio', label: '유동비율', kind: 'percent', chart: true },
    { key: 'interest_coverage', label: '이자보상배율', kind: 'multiple', chart: false }] },
  { name: '활동성', unit: 'x', metrics: [
    { key: 'asset_turnover', label: '총자산회전율', kind: 'multiple', chart: true },
    { key: 'receivable_turnover', label: '매출채권회전율', kind: 'multiple', chart: true },
    { key: 'inventory_turnover', label: '재고자산회전율', kind: 'multiple', chart: true }] },
  { name: '성장성', unit: '%', metrics: [
    { key: 'revenue_growth', label: '매출액증가율', kind: 'change', chart: true },
    { key: 'operating_income_growth', label: '영업이익증가율', kind: 'change', chart: true },
    { key: 'asset_growth', label: '총자산증가율', kind: 'change', chart: true }] },
]

export function Ratios({ r }: { r: ReportDetail }) {
  const years = yearsOf(r)
  const byFinancialCost = r.interest_basis === '금융비용'
  return (
    <section className={styles.card}>
      <h3>재무비율</h3>
      {GROUPS.map((g) => {
        const label = (m: MetricDef) => (m.key === 'interest_coverage' && byFinancialCost ? '이자보상배율(금융비용 기준)' : m.label)
        const metric = (m: MetricDef, y: number) => r.results.ratios[String(y)]?.[m.key]
        const rows = g.metrics.map((m) => ({ label: label(m), cells: years.map((y) => formatMetric(metric(m, y), m.kind)) }))
        const hasYearEnd = g.metrics.some((m) => years.some((y) => metric(m, y)?.value != null && metric(m, y)?.year_end_only))
        const charted = g.metrics.filter((m) => m.chart)
        const factor = g.unit === '%' ? 100 : 1
        const data = years.map((y) => Object.fromEntries([
          ['year', y], ...charted.map((m) => [m.key, (metric(m, y)?.value ?? null) === null ? null : (metric(m, y)!.value as number) * factor]),
        ]))
        return (
          <div key={g.name}>
            <YearTable title={g.name} years={years} rows={rows} footnote={<>
              {hasYearEnd && '† 평균 대신 기말 값 기준  '}
              {g.name === '안정성' && byFinancialCost && '이자보상배율은 이자비용 대신 금융비용으로 계산했습니다 (외환·파생상품 손실이 포함될 수 있음)  '}
              {g.chartNote}
            </>} />
            <LineGroupChart data={data} series={charted.map((m) => ({ key: m.key, name: label(m) }))} unit={g.unit} />
          </div>
        )
      })}
    </section>
  )
}

// ───────────────────────── 2페이지: 듀퐁
export function Dupont({ r }: { r: ReportDetail }) {
  const years = yearsOf(r)
  const d = (y: number) => r.results.dupont[String(y)]
  const reason = (y: number): string => {
    const driver = d(y)?.driver
    if (!driver) return d(y)?.driver_na ?? '자료 없음'
    return `${driver.factor} (${formatChange(driver.changes[driver.factor]).text})`
  }
  const latest = d(r.base_year)
  return (
    <section className={styles.card}>
      <h3>듀퐁 분석 <span className={styles.unit}>ROE = 순이익률 × 총자산회전율 × 재무레버리지</span></h3>
      <YearTable title="ROE 분해" years={years} rows={[
        { label: '순이익률', cells: years.map((y) => formatMetric(d(y)?.metrics.net_margin, 'percent')) },
        { label: '총자산회전율', cells: years.map((y) => formatMetric(d(y)?.metrics.asset_turnover, 'multiple')) },
        { label: '재무레버리지', cells: years.map((y) => formatMetric(d(y)?.metrics.leverage, 'multiple')) },
        { label: 'ROE', cells: years.map((y) => formatMetric(d(y)?.metrics.roe, 'percent')) },
        { label: '주된 변화 요인', cells: years.map((y) => reason(y)) },
      ]} footnote={d(years[0])?.metrics.roe?.year_end_only ? '† 평균 대신 기말 값 기준. 주된 변화 요인의 괄호 안은 그 요소의 전년 대비 변화율' : '주된 변화 요인의 괄호 안은 그 요소의 전년 대비 변화율'} />
      <p><b>ROE가 변한 주된 이유 ({r.base_year}):</b> {latest ? reason(r.base_year) : '자료 없음'}</p>
    </section>
  )
}

// ───────────────────────── 2페이지: 현금흐름
export function Cashflow({ r }: { r: ReportDetail }) {
  const years = yearsOf(r)
  const data = years.map((y) => ({
    year: y,
    cfo: (amount(fyOf(r, y), 'cfo') ?? NaN) / EOK, cfi: (amount(fyOf(r, y), 'cfi') ?? NaN) / EOK, cff: (amount(fyOf(r, y), 'cff') ?? NaN) / EOK,
  })).map((d) => ({ year: d.year, cfo: Number.isNaN(d.cfo) ? null : d.cfo, cfi: Number.isNaN(d.cfi) ? null : d.cfi, cff: Number.isNaN(d.cff) ? null : d.cff }))
  const row = (label: string, field: string) => ({ label, cells: years.map((y) => formatWonTable(amount(fyOf(r, y), field))) })
  return (
    <section className={styles.card}>
      <h3>현금흐름 패턴</h3>
      <CashflowChart data={data} />
      <YearTable title="현금흐름" unit="억 원" years={years} rows={[
        row('영업활동', 'cfo'), row('투자활동', 'cfi'), row('재무활동', 'cff'),
        { label: '패턴', cells: years.map((y) => r.results.cashflow[String(y)]?.pattern ?? r.results.cashflow[String(y)]?.na_reason ?? '자료 없음') },
      ]} />
    </section>
  )
}

export function Sources({ r }: { r: ReportDetail }) {
  return (
    <section className={styles.card}>
      <h3>출처 (DART 공시 원문)</h3>
      <ul className={styles.sources}>
        {r.sources.map((s) => (
          <li key={s.rcept_no + s.label}><a href={s.url} target="_blank" rel="noreferrer">{s.label}</a> <span className={styles.sub}>접수번호 {s.rcept_no}</span></li>
        ))}
      </ul>
    </section>
  )
}
