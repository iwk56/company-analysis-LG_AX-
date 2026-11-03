import { useState } from 'react'
import styles from '../app.module.css'
import { refreshArticles } from '../api'
import type { ApiError, ArticleList, ComparisonCell, ComparisonColumn, FinancialYear, MacroSeries, MetricMap, ReportDetail, StockSeries } from '../api'
import naverLogo from '../assets/naver-openapi-powered.png'
import { ARROW, difference, direction, relativeChange } from '../format/delta'
import type { Direction } from '../format/delta'
import type { Formatted, MetricKind } from '../format/number'
import {
  formatBaseRate, formatChange, formatExchangeRate, formatMetric, formatMultiple, formatPeople, formatPercent, formatPercentPoint, formatWonCard,
  formatPrice, formatWonMan, formatWonTable, formatYears, noData,
} from '../format/number'
import { dateText } from '../format/date'
import { naverParts } from '../format/naverText'
import { Num, SignalBadge } from '../ui'
import { AiBadge, InfoNote, NoteButton, NotePanel, Summary } from './ai'
import { evidenceFor, useContent, useNotice, useTopicMarks } from './aiData'
import { CashflowChart, ComparisonScatter, LineGroupChart, SegmentChart, SeriesChart, StockIndexChart, TrendChart } from './charts'
import { COLORS } from './palette'
import YearTable from './YearTable'
import { SectionCard } from './comments'
import { Sensitivity } from './external'
import { JumpLink } from './fold'
import { essayNumbers } from '../format/essayNumbers'

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

// ───────────────────────── 1장: 핵심 지표 카드
function Card({ label, value, signal, reason, dir, deltaText, noteKey, open, onNote }: {
  label: string
  value: Formatted
  signal: { level: string; reason: string } | null | undefined
  reason?: string
  dir: Direction | null
  deltaText: Formatted | null
  noteKey: string
  open: boolean
  onNote: () => void
}) {
  return (
    <div className={styles.metriccard}>
      <div className={styles.label}>{label} <NoteButton noteKey={noteKey} open={open} onToggle={onNote} /></div>
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
  const [openKey, setOpenKey] = useState<string | null>(null)
  const y = String(r.base_year)
  const p = String(r.base_year - 1)
  const ratio = (year: string, key: string) => r.results.ratios[year]?.[key]
  const sig = (key: string) => r.results.signals[y]?.[key]
  const note = (key: string) => ({ noteKey: key, open: openKey === key, onNote: () => setOpenKey(openKey === key ? null : key) })
  const ppCard = (key: string, label: string, signalKey: string, main: (m: MetricMap[string]) => Formatted) => {
    const d = difference(ratio(y, key)?.value, ratio(p, key)?.value)
    return (
      <Card label={label} value={main(ratio(y, key))} signal={sig(signalKey)} dir={direction(d)}
        deltaText={d === null ? null : formatPercentPoint(d)} {...note(key)} />
    )
  }
  const cfoDelta = relativeChange(amount(fyOf(r, r.base_year), 'cfo'), amount(fyOf(r, r.base_year - 1), 'cfo'))
  return (
    <SectionCard sectionKey="core_cards">
      <h3>핵심 지표 <span className={styles.unit}>{r.base_year} 사업연도</span></h3>
      <Summary sectionKey="core_cards" />
      <div className={styles.cards}>
        {ppCard('revenue_growth', '매출 성장률', 'revenue_growth', (m) => formatMetric(m, 'change'))}
        {ppCard('operating_margin', '영업이익률', 'operating_margin', (m) => formatMetric(m, 'percent'))}
        {ppCard('debt_ratio', '부채비율', 'debt_ratio', (m) => formatMetric(m, 'percent'))}
        <Card label="영업현금흐름" value={formatWonCard(amount(fyOf(r, r.base_year), 'cfo'))} signal={sig('operating_cashflow')}
          dir={direction(cfoDelta)} deltaText={cfoDelta === null ? null : formatChange(cfoDelta)} {...note('operating_cashflow')} />
      </div>
      {openKey && <NotePanel noteKey={openKey} />}
    </SectionCard>
  )
}

// ───────────────────────── 2장: 최근 실적 박스
export function RecentBox({ r }: { r: ReportDetail }) {
  const rr = r.recent_results
  if (!rr) {
    return (
      <SectionCard sectionKey="recent_results">
        <h3>최근 실적</h3>
        <p className={styles.muted}>{r.recent_reason ?? '아직 제출된 반기·3분기 보고서가 없습니다'}</p>
      </SectionCard>
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
    <SectionCard sectionKey="recent_results">
      <h3>최근 실적 <span className={styles.unit}>{rr.year}년 {rr.report_name}보고서 · {rr.basis}재무제표 · 누적</span></h3>
      <Summary sectionKey="recent_results" />
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
      <NetVsOperating r={r} />
      {source && <p className={styles.footnote}>출처: <a href={source.url} target="_blank" rel="noreferrer">{source.label}</a></p>}
    </SectionCard>
  )
}

// ───────────────────────── 부록 C: 실적 추이 + 재무 수치 표
export function Trend({ r }: { r: ReportDetail }) {
  const years = yearsOf(r)
  const data = years.map((year) => ({
    year,
    revenue: (amount(fyOf(r, year), 'revenue') ?? NaN) / EOK,
    margin: (r.results.ratios[String(year)]?.operating_margin?.value ?? NaN) * 100,
  })).map((d) => ({ ...d, revenue: Number.isNaN(d.revenue) ? null : d.revenue, margin: Number.isNaN(d.margin) ? null : d.margin }))
  const row = (label: string, field: string) => ({ label, cells: years.map((y) => formatWonTable(amount(fyOf(r, y), field))) })
  return (
    <SectionCard sectionKey="trend">
      <h3>실적 추이</h3>
      <Summary sectionKey="trend" />
      <TrendChart data={data} />
      <YearTable title="재무 수치" unit="억 원" years={years}
        rows={[row('매출액', 'revenue'), row('영업이익', 'operating_income'), row('당기순이익', 'net_income'),
          row('지배주주 순이익', 'net_income_parent'), row('자산총계', 'total_assets'), row('부채총계', 'total_liabilities'),
          row('자본총계', 'total_equity')]} />
    </SectionCard>
  )
}

// ───────────────────────── 부록 C: 재무비율 (그룹별 표 + 선 차트)
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
    <SectionCard sectionKey="ratios">
      <h3>재무비율</h3>
      <Summary sectionKey="ratios" />
      {GROUPS.map((g) => {
        const label = (m: MetricDef) => (m.key === 'interest_coverage' && byFinancialCost ? '이자보상배율(금융비용 기준)' : m.label)
        const metric = (m: MetricDef, y: number) => r.results.ratios[String(y)]?.[m.key]
        const rows = g.metrics.map((m) => ({ label: label(m), cells: years.map((y) => formatMetric(metric(m, y), m.kind)), noteKey: m.key }))
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
            {g.name === '안정성' && <ActualInterest r={r} />}
            <LineGroupChart data={data} series={charted.map((m) => ({ key: m.key, name: label(m) }))} unit={g.unit} />
          </div>
        )
      })}
    </SectionCard>
  )
}

// ───────────────────────── 부록 C: 듀퐁
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
    <SectionCard sectionKey="dupont">
      <h3>듀퐁 분석 <span className={styles.unit}>ROE = 순이익률 × 총자산회전율 × 재무레버리지</span></h3>
      <Summary sectionKey="dupont" />
      <YearTable title="ROE 분해" years={years} rows={[
        { label: '순이익률', cells: years.map((y) => formatMetric(d(y)?.metrics.net_margin, 'percent')) },
        { label: '총자산회전율', cells: years.map((y) => formatMetric(d(y)?.metrics.asset_turnover, 'multiple')) },
        { label: '재무레버리지', cells: years.map((y) => formatMetric(d(y)?.metrics.leverage, 'multiple')) },
        { label: 'ROE', cells: years.map((y) => formatMetric(d(y)?.metrics.roe, 'percent')) },
        { label: '주된 변화 요인', cells: years.map((y) => reason(y)) },
      ]} footnote={d(years[0])?.metrics.roe?.year_end_only ? '† 평균 대신 기말 값 기준. 주된 변화 요인의 괄호 안은 그 요소의 전년 대비 변화율' : '주된 변화 요인의 괄호 안은 그 요소의 전년 대비 변화율'} />
      <div><b>ROE가 변한 주된 이유 ({r.base_year}):</b> {latest ? reason(r.base_year) : '자료 없음'} <InfoNote noteKey="roe" /></div>
    </SectionCard>
  )
}

// ───────────────────────── 부록 C: 현금흐름
export function Cashflow({ r }: { r: ReportDetail }) {
  const years = yearsOf(r)
  const data = years.map((y) => ({
    year: y,
    cfo: (amount(fyOf(r, y), 'cfo') ?? NaN) / EOK, cfi: (amount(fyOf(r, y), 'cfi') ?? NaN) / EOK, cff: (amount(fyOf(r, y), 'cff') ?? NaN) / EOK,
  })).map((d) => ({ year: d.year, cfo: Number.isNaN(d.cfo) ? null : d.cfo, cfi: Number.isNaN(d.cfi) ? null : d.cfi, cff: Number.isNaN(d.cff) ? null : d.cff }))
  const row = (label: string, field: string) => ({ label, cells: years.map((y) => formatWonTable(amount(fyOf(r, y), field))) })
  return (
    <SectionCard sectionKey="cashflow">
      <h3>현금흐름 패턴</h3>
      <Summary sectionKey="cashflow" />
      <CashflowChart data={data} />
      <YearTable title="현금흐름" unit="억 원" years={years} rows={[
        { ...row('영업활동', 'cfo'), noteKey: 'operating_cashflow' }, row('투자활동', 'cfi'), row('재무활동', 'cff'),
        { label: '패턴', cells: years.map((y) => r.results.cashflow[String(y)]?.pattern ?? r.results.cashflow[String(y)]?.na_reason ?? '자료 없음'), noteKey: 'cashflow_pattern' },
      ]} />
    </SectionCard>
  )
}

// ───────────────────────── 부록 E: 경쟁사 비교 (표의 열은 응답의 columns를 보고 그린다)
const AVG_MARK = { above: '▲', below: '▼', same: '＝' } as const
const AVG_TITLE = { above: '평균보다 높음', below: '평균보다 낮음', same: '평균과 같음' } as const

function cellValue(col: ComparisonColumn, value: number | null, naReason: string | null = null): Formatted {
  if (value === null) return noData(naReason ?? undefined)
  if (col.format === 'amount') return formatWonTable(value)
  if (col.format === 'multiple') return formatMultiple(value)
  return col.format === 'change' ? formatChange(value) : formatPercent(value)
}

function CompareCell({ col, cell }: { col: ComparisonColumn; cell: ComparisonCell }) {
  return (
    <td>
      <Num f={cellValue(col, cell.value, cell.na_reason)} />
      {cell.vs_average && <span title={AVG_TITLE[cell.vs_average]}> {AVG_MARK[cell.vs_average]}</span>}
      {cell.rank !== null && <span className={styles.sub}> {cell.rank}위</span>}
    </td>
  )
}

const percentOrNull = (v: number | null | undefined) => (typeof v === 'number' ? v * 100 : null)

export function Competitors({ r }: { r: ReportDetail }) {
  const comp = r.results.comparison
  if (!comp) {
    return (
      <SectionCard sectionKey="competitors">
        <h3>경쟁사 비교</h3>
        <p className={styles.muted}>이 리포트는 경쟁사 없이 만들어졌습니다.</p>
      </SectionCard>
    )
  }
  const point = (p: { corp_name: string; x: number; y: number }) => ({ corp_name: p.corp_name, x: p.x * 100, y: p.y * 100 })
  return (
    <SectionCard sectionKey="competitors">
      <h3>경쟁사 비교 <span className={styles.unit}>({comp.base_year} 사업연도 기준)</span></h3>
      <Summary sectionKey="competitors" />
      <p className={styles.sub}>업계 내 위치 한 줄과 시가총액 순위는 <JumpLink to="position">1장 업계 위치</JumpLink>에 있습니다.</p>
      <div className={styles.tablescroll}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th>기업</th>
            {comp.columns.map((c) => <th key={c.key}>{c.label}{c.format === 'amount' ? ' (억 원)' : ''}</th>)}
          </tr>
        </thead>
        <tbody>
          {comp.rows.map((row) => (
            <tr key={row.corp_code} className={row.is_target ? styles.targetrow : undefined}>
              <td>
                {row.corp_name}{row.is_target && ' (분석 기업)'}{' '}
                <span className={styles.sub}>{row.basis}</span>
                {row.source_url && <> <a href={row.source_url} target="_blank" rel="noreferrer">원문</a></>}
              </td>
              {comp.columns.map((c) => <CompareCell key={c.key} col={c} cell={row.values[c.key]} />)}
            </tr>
          ))}
          <tr>
            <td>평균 (분석 기업 포함)</td>
            {comp.columns.map((c) => <td key={c.key}><Num f={cellValue(c, comp.averages[c.key] ?? null)} /></td>)}
          </tr>
        </tbody>
      </table>
      </div>
      <p className={styles.footnote}>
        ▲▼는 해당 칸이 평균보다 높은지 낮은지입니다(좋고 나쁨이 아님). 순위는 1위가 가장 좋은 쪽이며 부채비율은 낮을수록 1위입니다(시가총액은 큰 쪽이 1위인 규모 순위).
        {' '}{comp.rank_rule}
      </p>
      <MarketNotes r={r} />
      {comp.excluded.map((x) => <p key={x.corp_code} className={styles.notice}>{x.corp_name}: {x.reason}</p>)}
      {comp.scatter.length > 0 && (
        <>
          <p className={styles.tabletitle}>성장률 × 이익률</p>
          <ComparisonScatter
            target={comp.scatter.filter((p) => p.is_target).map(point)}
            others={comp.scatter.filter((p) => !p.is_target).map(point)}
            averageX={percentOrNull(comp.averages.revenue_growth)} averageY={percentOrNull(comp.averages.operating_margin)} />
        </>
      )}
    </SectionCard>
  )
}

/** 비교표의 시가총액 설명 (5-B 이후 리포트에만). PER·PBR 설명은 부록 D(Valuation)에 있다 */
function MarketNotes({ r }: { r: ReportDetail }) {
  const comp = r.results.comparison
  if (!comp || !comp.columns.some((c) => c.key === 'market_cap')) return null
  const dates = [...new Set(comp.rows.map((row) => row.market_as_of).filter((d): d is string => !!d))].sort()
  return (
    <div className={styles.footnote}>
      <p>
        시가총액은 <b>보통주 기준</b>입니다(공공데이터포털 금융위원회_주식시세정보, 기준일 {dates.length ? dates.join(', ') : '자료 없음'}).
        {' '}우선주가 있는 기업은 포털 시가총액보다 작게 나올 수 있습니다. PER·PBR 계산 방법은 <JumpLink to="stocks">부록 D 가치평가</JumpLink>에 있습니다.
      </p>
    </div>
  )
}

/** 부록 D 맨 위: 분석 기업의 시가총액·PER·PBR 한 줄 (경쟁사 비교표의 같은 값) + PER·PBR 설명 */
function Valuation({ r }: { r: ReportDetail }) {
  const comp = r.results.comparison
  const row = comp?.rows.find((x) => x.is_target)
  const cols = comp?.columns.filter((c) => ['market_cap', 'per', 'pbr'].includes(c.key)) ?? []
  if (!comp || !row || cols.length === 0) return <p className={styles.muted}>시가총액·PER·PBR: 시세 없음</p>
  const show = (c: ComparisonColumn) => {
    const cell = row.values[c.key]
    return c.key === 'market_cap' ? formatWonCard(cell?.value) : cellValue(c, cell?.value ?? null, cell?.na_reason ?? null)
  }
  return (
    <>
      <p>
        <b>{row.corp_name}</b>{' '}
        {cols.map((c, i) => <span key={c.key}>{i > 0 && ' · '}{c.label} <b><Num f={show(c)} /></b>{c.key !== 'market_cap' && <> <InfoNote noteKey={c.key} /></>}</span>)}
        {' '}<span className={styles.sub}>(기준일 {row.market_as_of ?? '자료 없음'}, 보통주 기준)</span>
      </p>
      <p className={styles.footnote}>
        PER = 시가총액 ÷ {comp.base_year} 지배주주 순이익, PBR = 시가총액 ÷ {comp.base_year}말 지배주주 자본(계산은 코드). 경쟁사 값은 <JumpLink to="competitors">부록 E 경쟁사 비교</JumpLink>.
        {' '}포털·증권사 앱은 보통 최근 4개 분기 이익을 써서 값이 다를 수 있습니다.
      </p>
    </>
  )
}

// ───────────────────────── 1장: 업계 위치 (경쟁사 비교에서 계산한 값을 그대로, 새 계산 없음, 코멘트란 없음)
export function Position({ r }: { r: ReportDetail }) {
  const comp = r.results.comparison
  const row = comp?.rows.find((x) => x.is_target)
  const cap = row?.values.market_cap
  return (
    <section className={styles.card} data-section="position">
      <h3>업계 위치 {comp && <span className={styles.unit}>({comp.base_year} 사업연도 · 비교 기업 평균 대비)</span>}</h3>
      {!comp ? <p className={styles.muted}>경쟁사 없이 만들어진 리포트입니다.</p> : (
        <>
          <p>
            {cap && cap.rank !== null ? (
              <>시가총액 <b><Num f={formatWonCard(cap.value)} /></b> · 비교 기업 {comp.ranked_counts.market_cap}곳 중 <b>{cap.rank}위</b>{' '}
                <span className={styles.sub}>(기준일 {row?.market_as_of ?? '자료 없음'}, 보통주 기준)</span></>
            ) : <>시가총액 순위: <span className={styles.muted}>시세 없음</span></>}
          </p>
          <p><b>{comp.position.text}</b></p>
          <p className={styles.sub}>비교표·점 그래프: <JumpLink to="competitors">부록 E 경쟁사 비교</JumpLink></p>
        </>
      )}
    </section>
  )
}

// ───────────────────────── 부록 D: 주가 흐름 비교 (기준일 = 100)
function stockRows(list: StockSeries[]) {
  const byDate = new Map<string, Record<string, number | string | null>>()
  for (const s of list) {
    for (const p of s.points) {
      const row = byDate.get(p.date) ?? { date: p.date }
      row[s.corp_code] = p.index
      byDate.set(p.date, row)
    }
  }
  return [...byDate.values()].sort((a, b) => String(a.date).localeCompare(String(b.date)))
}

export function Stocks({ r }: { r: ReportDetail }) {
  const list = r.stocks ?? null
  const marks = useTopicMarks()
  const withData = (list ?? []).filter((s) => s.points.length > 0)
  return (
    <SectionCard sectionKey="stocks">
      <h3>주가 흐름 비교 <span className={styles.unit}>(최근 1년, 기준일 종가 = 100)</span></h3>
      <Valuation r={r} />
      {list === null ? (
        <p className={styles.muted}>이 리포트는 주가 수집 기능이 생기기 전에 만들어져 자료가 없습니다. 리포트를 다시 만들면 표시됩니다.</p>
      ) : (
        <>
          {withData.length > 0 && (
            <StockIndexChart data={stockRows(withData)} lines={withData.map((s) => ({ key: s.corp_code, name: s.corp_name, isTarget: s.is_target }))} marks={marks} />
          )}
          <ul className={styles.sources}>
            {list.map((s) => {
              const first = s.points[0]
              const last = s.points[s.points.length - 1]
              return (
                <li key={s.corp_code}>
                  <b>{s.corp_name}</b>{s.is_target && ' (분석 기업)'}{' '}
                  {first && last ? (
                    <>기준일 {first.date} {formatPrice(first.close).text} → {last.date} {formatPrice(last.close).text} (지수 {last.index.toFixed(1)})</>
                  ) : <span className={styles.muted}>시세 없음</span>}
                  {s.notes.map((n) => <div key={n} className={styles.sub}>{n}</div>)}
                </li>
              )
            })}
          </ul>
          <p className={styles.footnote}>
            {marks.length > 0 && <>보라색 세로 점선 ①②③은 <JumpLink to="topics">2장 공시 주제</JumpLink>의 공시 날짜입니다(휴일이면 다음 거래일). </>}
            수정주가가 아니라 액면분할·배당 등이 반영되지 않았을 수 있습니다. 기준일은 리포트 생성일 1년 전 이후 첫 거래일이며, 보통주 종가 기준입니다.
            {' '}출처: <a href="https://www.data.go.kr/data/15094808/openapi.do" target="_blank" rel="noreferrer">공공데이터포털 금융위원회_주식시세정보</a> (영업일 1~2일 늦게 반영)
          </p>
        </>
      )}
    </SectionCard>
  )
}

// ───────────────────────── 주석에서 AI로 추출한 실제 이자비용 → 이자보상배율 보강
function ActualInterest({ r }: { r: ReportDetail }) {
  const fin = useContent('extract_finance')
  const notice = useNotice('extract_finance')
  const link = evidenceFor(r, 'interest_coverage')[0]
  if (!fin || fin.interest_expense_won === null) {
    return notice ? <p className={styles.footnote}>실제 이자비용(주석): {notice.message}</p> : null
  }
  return (
    <p className={styles.footnote}>
      <AiBadge task="extract_finance" kind="extract" /> 주석의 실제 이자비용 <b>{formatWonCard(fin.interest_expense_won).text}</b> 기준 이자보상배율({r.base_year}):{' '}
      <b>{formatMultiple(fin.coverage_actual).text}</b> (영업이익 ÷ 실제 이자비용, 계산은 코드)
      {link && <> · <a href={link.url} target="_blank" rel="noreferrer">원문</a></>}
      {r.interest_basis === '금융비용' && ' — 위 표의 금융비용 기준 값과 차이가 큰 것은 금융비용에 외환·파생상품 손실이 섞이기 때문입니다'}
    </p>
  )
}

// ───────────────────────── 순이익이 영업이익보다 큰 경우의 원인 (금융수익 등 영업외 항목)
function NetVsOperating({ r }: { r: ReportDetail }) {
  const fin = useContent('extract_finance')
  const n = fin?.net_vs_operating
  if (!n) return null
  const link = evidenceFor(r, 'net_vs_operating')[0]
  return (
    <div className={styles.explain}>
      <b>순이익이 영업이익보다 큰 이유</b> <InfoNote noteKey="net_vs_operating" />
      <p>
        {n.period_label} 지배주주 순이익 <b>{formatWonCard(n.net_income_parent).text}</b>이 영업이익 <b>{formatWonCard(n.operating_income).text}</b>보다 큽니다.
        본업 실적은 영업이익 기준으로 봐야 합니다.
      </p>
      {n.items.length > 0 ? (
        <p><AiBadge task="extract_finance" kind="extract" /> 주석의 금융수익 주요 항목(누적): {n.items.map((i) => `${i.label} ${formatWonCard(i.amount_won).text}`).join(', ')}
          {link && <> · <a href={link.url} target="_blank" rel="noreferrer">원문</a></>}</p>
      ) : (
        <p className={styles.muted}>주석의 금융수익 항목은 원문과 대조하지 못해 표시하지 않습니다.</p>
      )}
    </div>
  )
}

// ───────────────────────── 1장: 기업 개요 + 직원·연구개발비
function Fact({ label, value, extra }: { label: string; value: Formatted; extra?: React.ReactNode }) {
  return (
    <div className={styles.fact}>
      <div className={styles.label}>{label}</div>
      <div className={styles.factvalue}><Num f={value} /></div>
      {extra && <div className={styles.footnote}>{extra}</div>}
    </div>
  )
}

export function Overview({ r }: { r: ReportDetail }) {
  const ov = useContent('write_overview')
  const ovNotice = useNotice('write_overview')
  const emp = useContent('employees')
  const empNotice = useNotice('employees')
  const rnd = useContent('extract_rnd')
  const rndNotice = useNotice('extract_rnd')
  const link = evidenceFor(r, 'rnd')[0]
  const missing = (msg?: string) => noData(msg ? `자료 없음` : '자료 없음')
  return (
    <SectionCard sectionKey="overview">
      <h3>기업 개요</h3>
      <p className={styles.sub}>업종 {r.company.industry_name ?? '자료 없음'}</p>
      {ov?.overview ? <p><AiBadge task="write_overview" /> {ov.overview}</p> : <p className={styles.muted}>{ovNotice?.message ?? 'AI 기업 개요가 아직 없습니다'}</p>}
      <div className={styles.facts}>
        <Fact label="직원 수" value={emp ? formatPeople(emp.count) : missing(empNotice?.message)}
          extra={emp ? <>{emp.year}년 사업보고서 기준{emp.url && <> · <a href={emp.url} target="_blank" rel="noreferrer">원문</a></>}</> : empNotice?.message} />
        <Fact label="평균 근속연수" value={emp ? formatYears(emp.avg_tenure_years) : missing()} />
        <Fact label="평균 급여(1인)" value={emp ? formatWonMan(emp.avg_salary_won) : missing()} />
        <Fact label="연구개발비" value={rnd ? formatWonCard(rnd.amount_won) : missing(rndNotice?.message)}
          extra={rnd ? <><AiBadge task="extract_rnd" kind="extract" /> 매출 대비 {formatPercent(rnd.ratio_to_revenue).text}(계산은 코드){link && <> · <a href={link.url} target="_blank" rel="noreferrer">원문</a></>}</> : rndNotice?.message} />
      </div>
      <p className={styles.footnote}>직원 현황은 사업보고서 기준이며 연결이 아니라 보고서를 낸 회사(보통 별도) 기준입니다. 남·여 값을 직원 수로 가중해 합산한 값이라 원문 합계와 약간 다를 수 있습니다.</p>
    </SectionCard>
  )
}

// ───────────────────────── 1장: 사업부문 비중 + BCG 해석
export function Segments({ r }: { r: ReportDetail }) {
  const seg = useContent('extract_segments')
  const notice = useNotice('extract_segments')
  const bcg = useContent('write_overview')?.bcg
  const link = evidenceFor(r, 'segments')[0]
  if (!seg || seg.products.length === 0) {
    return (
      <SectionCard sectionKey="segments">
        <h3>사업부문 비중</h3>
        <p className={styles.muted}>{notice?.message ?? (seg ? '원문에서 사업부문(품목)별 매출을 확인하지 못했습니다' : '사업부문 자료가 아직 없습니다')}</p>
        {seg?.overseas_share != null && <p>해외 매출 비중(지역별 매출 기준) <b>{formatPercent(seg.overseas_share).text}</b></p>}
      </SectionCard>
    )
  }
  return (
    <SectionCard sectionKey="segments">
      <h3>사업부문(품목)별 매출 비중 <span className={styles.unit}>{seg.year} 사업연도</span> <AiBadge task="extract_segments" kind="extract" /></h3>
      <Summary sectionKey="segments" />
      <SegmentChart data={seg.products.map((p) => ({ name: p.name, share: (p.share ?? 0) * 100 }))} />
      <table className={styles.table}>
        <thead><tr><th>부문</th><th>매출액(억 원)</th><th>비중</th><th>전년 대비</th></tr></thead>
        <tbody>
          {seg.products.map((p) => (
            <tr key={p.name}><td>{p.name}</td><td><Num f={formatWonTable(p.current_won)} /></td><td><Num f={formatPercent(p.share)} /></td>
              <td><Num f={formatChange(p.growth)} /></td></tr>
          ))}
        </tbody>
      </table>
      {seg.overseas_share !== null && (
        <p>해외 매출 비중 <b>{formatPercent(seg.overseas_share).text}</b> <span className={styles.sub}>(지역별 매출에서 국내를 뺀 값, 수출 통계와는 다를 수 있음)</span></p>
      )}
      {bcg && (
        <div className={styles.explain}>
          <b>BCG 관점 해석</b> <AiBadge task="write_overview" />
          {bcg.summary && <p>{bcg.summary}</p>}
          {bcg.segments.length > 0 && <ul>{bcg.segments.map((s) => <li key={s.name}><b>{s.name}</b>: {s.comment}</li>)}</ul>}
          <p className={styles.footnote}>시장점유율 자료가 없어 BCG 매트릭스로 분류하지 않고, 매출 비중과 성장 속도만으로 해석했습니다.</p>
        </div>
      )}
      <p className={styles.footnote}>
        금액은 사업보고서 주석에서 AI가 옮긴 값을 원문과 대조해 쓴 것이고, 비중·증감률은 코드가 계산했습니다.
        {link && <> 출처: <a href={link.url} target="_blank" rel="noreferrer">{link.label}</a></>}
      </p>
    </SectionCard>
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

// ───────────────────────── 부록 A: 환율·기준금리
const MACRO_VIEW: Record<string, { format: (v: number) => Formatted; color: string; step: boolean }> = {
  usd_krw: { format: formatExchangeRate, color: COLORS[0], step: false },
  base_rate: { format: formatBaseRate, color: COLORS[1], step: true },
}

function MacroChart({ series }: { series: MacroSeries }) {
  const view = MACRO_VIEW[series.key] ?? { format: (v: number) => noData(String(v)), color: COLORS[0], step: false }
  const last = series.points.at(-1)
  return (
    <>
      <h4 className={styles.tabletitle}>{series.label}</h4>
      {last ? (
        <>
          <p className={styles.sub}>최근 값 <b><Num f={view.format(last.value)} /></b> ({last.date}) · 조회 기간 {series.period_start} ~ {series.period_end}</p>
          <SeriesChart points={series.points} name={series.label} format={view.format} color={view.color} step={view.step} />
        </>
      ) : (
        <p className={styles.muted}>조회 기간({series.period_start} ~ {series.period_end})에 자료가 없습니다.</p>
      )}
      <p className={styles.footnote}>
        출처: <a href={series.source_url} target="_blank" rel="noreferrer">한국은행 ECOS</a> (통계표 {series.stat_code})
      </p>
    </>
  )
}

export function Macro({ r }: { r: ReportDetail }) {
  return (
    <SectionCard sectionKey="macro">
      <h3>경제 환경 민감도 <span className={styles.unit}>(환율·기준금리 최근 1년)</span></h3>
      <Summary sectionKey="macro" />
      {r.macro === null ? (
        <p className={styles.muted}>이 리포트는 환율·금리 수집 기능이 생기기 전에 만들어져 자료가 없습니다. 리포트를 다시 만들면 표시됩니다.</p>
      ) : (
        r.macro.map((s) => <MacroChart key={s.key} series={s} />)
      )}
      <Sensitivity />
    </SectionCard>
  )
}

// ───────────────────────── 2장 마지막: 네이버 검색결과 (참고 목록, AI에 넣지 않음)
const NAVER_API_HUB_URL = 'https://www.ncloud.com/product/applicationService/NAVERAPIHUB'

function NaverText({ raw }: { raw: string }) {
  return <>{naverParts(raw).map((p, i) => (p.bold ? <b key={i}>{p.text}</b> : <span key={i}>{p.text}</span>))}</>
}

export function Articles({ r }: { r: ReportDetail }) {
  const [a, setA] = useState<ArticleList | null>(r.articles)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const reload = () => {
    setLoading(true)
    setError(null)
    refreshArticles(r.id)
      .then((res) => setA(res.articles))
      .catch((e: ApiError) => setError(e.message))
      .finally(() => setLoading(false))
  }
  // 약관(검색결과 앞뒤에 다른 내용 삽입 금지)에 따라 내 코멘트란이 붙는 SectionCard를 쓰지 않는다
  return (
    <section className={styles.card}>
      <h3>네이버 검색결과 <span className={styles.unit}>(참고 목록{a && !a.expired && ', 최신순 30건'})</span></h3>
      {a === null ? (
        <p className={styles.muted}>이 리포트는 기사 수집 기능이 생기기 전에 만들어져 자료가 없습니다. 리포트를 다시 만들면 표시됩니다.</p>
      ) : a.expired ? (
        <p className={styles.muted}>
          수집한 지 21일이 지나 기사를 지웠습니다 (네이버 검색 API 약관의 보관 기간).{' '}
          <button className={styles.link} disabled={loading} onClick={reload}>{loading ? '불러오는 중…' : '다시 불러오기'}</button>
          {error && <span className={styles.error}> {error}</span>}
        </p>
      ) : (
        <>
          <p className={styles.footnote}>
            회사명 “{a.query}”의 네이버 뉴스 검색결과(최신순 30건)를 받은 순서·내용 그대로 보여주는 참고 목록입니다. 리포트의 AI 해석에는 쓰지 않습니다.
            수집일 {dateText(a.collected_at)}, 약관에 따라 {dateText(a.expires_at)}에 지웁니다.
          </p>
          {a.items.length === 0 ? (
            <p className={styles.muted}>검색결과 없음</p>
          ) : (
            <ul className={styles.articles}>
              {a.items.map((it, i) => (
                <li key={i}>
                  <a href={it.link} target="_blank" rel="noreferrer"><NaverText raw={it.title} /></a>
                  <span className={styles.sub}> {dateText(it.published_at)}</span>
                  {it.summary && <p className={styles.summary}><NaverText raw={it.summary} /></p>}
                </li>
              ))}
            </ul>
          )}
        </>
      )}
      <p className={styles.naverbi}>
        <a href={NAVER_API_HUB_URL} target="_blank" rel="noreferrer">
          <img src={naverLogo} alt="NAVER 오픈 API" height={14} />
        </a>
        <span className={styles.footnote}>네이버™는 NAVER®의 등록상표입니다.</span>
      </p>
    </section>
  )
}

// ───────────────────────── 4장: 자기소개서에 쓸 숫자 모음 (코드가 저장된 값에서 고름, AI 없음 → 한 줄 요약 없음)
export function EssayNumbers({ r }: { r: ReportDetail }) {
  const { lines, excluded } = essayNumbers(r)
  return (
    <SectionCard sectionKey="essay_numbers">
      <h3>자기소개서에 쓸 숫자 모음 <span className={styles.unit}>(이미 계산·검증된 값, AI 없음)</span></h3>
      {lines.length === 0 ? <p className={styles.muted}>쓸 수 있는 숫자가 없습니다</p> : (
        <ul className={styles.essaylist}>
          {lines.map((l) => (
            <li key={l.key}>
              {l.lead} <b><Num f={l.value} /></b>{l.tail}
              <span className={styles.sub}>
                {' '}· {l.basis ? `${l.basis} 기준 · ` : ''}
                {l.source ? <a href={l.source.url} target="_blank" rel="noreferrer">{l.source.label}</a> : '출처 없음'}
              </span>
            </li>
          ))}
        </ul>
      )}
      {excluded.length > 0 && <p className={styles.footnote}>제외: {excluded.map((x) => `${x.label}(${x.reason})`).join(', ')}</p>}
      <p className={styles.footnote}>값과 숫자 표시는 다른 섹션과 같습니다. 해석·평가 표현은 넣지 않았으니 문장은 직접 쓰세요.</p>
    </SectionCard>
  )
}
