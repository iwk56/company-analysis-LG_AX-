// 손익계산서 분석 (2026-11-04, 실적 탭). 한 해의 경영성과를 '매출 → 매출총이익 → 영업이익 → 세전이익 → 순이익' 단계로 본다.
// 숫자는 모두 백엔드 calc/income.py가 계산한 값. 공시에 없는 단계(매출총이익·판관비)는 계산으로 채우고 표시한다.
import type { NoteRow, ReportDetail } from '../api'
import styles from '../app.module.css'
import { formatChange, formatPercent, formatWonCardDelta, formatWonTable, formatWonTableDelta } from '../format/number'
import { Num } from '../ui'
import { AiBadge, AnalysisPoints, InfoNote, Summary } from './ai'
import { useContent } from './aiData'
import { LineGroupChart } from './charts'
import { SectionCard } from './comments'
import YearTable from './YearTable'

type Rows = Record<string, number | null>
interface IncomeYear {
  rows: Rows
  margins: Rows
  effective_tax_rate: number | null
  derived: string[]
  bridge: { total: number; volume: number; margin: number; sga: number; other: number } | null
}

const STEPS: { key: string; label: string; level: 0 | 1 | 2; strong?: boolean; sign?: -1 }[] = [
  { key: 'revenue', label: '매출액', level: 0, strong: true },
  { key: 'cost_of_sales', label: '(−) 매출원가', level: 1, sign: -1 },
  { key: 'gross_profit', label: '매출총이익', level: 0, strong: true },
  { key: 'sga', label: '(−) 판매비와관리비', level: 1, sign: -1 },
  { key: 'other_operating', label: '(±) 기타 영업손익', level: 1 },
  { key: 'operating_income', label: '영업이익', level: 0, strong: true },
  { key: 'non_operating', label: '(±) 영업외손익', level: 1 },
  { key: 'finance_net', label: '└ 금융손익 (금융수익 − 금융비용)', level: 2 },
  { key: 'other_non_operating', label: '└ 기타 (지분법·외환·처분손익 등)', level: 2 },
  { key: 'pretax_income', label: '법인세비용차감전순이익', level: 0, strong: true },
  { key: 'income_tax', label: '(−) 법인세비용', level: 1, sign: -1 },
  { key: 'net_income', label: '당기순이익', level: 0, strong: true },
]

const MARGINS = [
  { key: 'gross_profit', name: '매출총이익률' },
  { key: 'sga', name: '판관비율' },
  { key: 'operating_income', name: '영업이익률' },
  { key: 'pretax_income', name: '세전이익률' },
  { key: 'net_income', name: '순이익률' },
]

export function IncomeStatement({ r }: { r: ReportDetail }) {
  const inc = r.results.income as Record<string, IncomeYear> | undefined // 예전 리포트에는 없다
  const y = r.base_year
  const cur = inc?.[String(y)]
  if (!inc || !cur) {
    return (
      <SectionCard sectionKey="income">
        <h3>손익계산서 분석</h3>
        <p className={styles.muted}>이 리포트는 손익계산서 분석 기능 이전에 만들어졌습니다. 같은 회사로 리포트를 새로 만들면 보입니다.</p>
      </SectionCard>
    )
  }
  const prev = inc[String(y - 1)]
  const years = Object.keys(inc).map(Number).sort()
  const shown = STEPS.filter((s) => cur.rows[s.key] !== null && cur.rows[s.key] !== undefined && !(s.key === 'other_operating' && !cur.rows[s.key]))
  const chartData = years.map((yr) => ({ year: yr, ...Object.fromEntries(MARGINS.map((m) => { const v = inc[String(yr)].margins[m.key]; return [m.key, v === null ? null : v * 100] })) })) // 차트는 % 숫자(48.6)를 받는다
  const derived = cur.derived.map((d) => (d === 'gross_profit' ? '매출총이익(매출 − 매출원가)' : d === 'sga' ? '판관비(매출총이익 − 영업이익, 기타 영업손익 포함)' : d))
  const b = cur.bridge
  return (
    <SectionCard sectionKey="income">
      <h3>손익계산서 분석 <span className={styles.unit}>({y} 사업연도 · {r.basis}재무제표)</span></h3>
      <Summary sectionKey="income" />

      <p className={styles.tabletitle}>매출이 이익으로 바뀌는 단계 <span className={styles.unit}>(단위: 억 원 · 매출 대비 % · 전년 대비)</span></p>
      <div className={styles.tablescroll}>
        <table className={styles.table}>
          <thead>
            <tr><th>단계</th>{prev && <th>{y - 1}</th>}<th>{y}</th><th>매출 대비</th>{prev && <th>전년 대비</th>}</tr>
          </thead>
          <tbody>
            {shown.map((s) => {
              const v = cur.rows[s.key]
              const p = prev?.rows[s.key] ?? null
              const ch = p !== null && v !== null && p > 0 && v >= 0 ? (v - p) / p : null
              return (
                <tr key={s.key} className={s.strong ? styles.incstrong : undefined}>
                  <td className={s.level === 1 ? styles.incsub : s.level === 2 ? styles.incsub2 : undefined}>{s.label}</td>
                  {prev && <td><Num f={formatWonTable(p)} /></td>}
                  <td><Num f={formatWonTable(v)} /></td>
                  <td>{s.key === 'revenue' ? '100%' : <Num f={formatPercent(cur.margins[s.key])} />}</td>
                  {prev && <td>{ch === null ? (p !== null && v !== null && p < 0 !== v < 0 ? (v >= 0 ? '흑자전환' : '적자전환') : '–') : <Num f={formatChange(ch)} />}</td>}
                </tr>
              )
            })}
            {cur.effective_tax_rate !== null && (
              <tr><td className={styles.incsub}>유효세율 (법인세 ÷ 세전이익)</td>{prev && <td><Num f={formatPercent(prev.effective_tax_rate)} /></td>}
                <td><Num f={formatPercent(cur.effective_tax_rate)} /></td><td /><td /></tr>
            )}
          </tbody>
        </table>
      </div>

      {b && (
        <div className={styles.part}>
          <div className={styles.parttitle}>영업이익은 왜 {b.total >= 0 ? '늘었나' : '줄었나'} ({y - 1} → {y}, {formatWonCardDelta(b.total).text}) <InfoNote noteKey="operating_margin" /></div>
          <ul className={styles.bridge}>
            <li><span>매출이 늘어난 효과</span><Num f={formatWonCardDelta(b.volume)} /><small>매출 증감 × 전년 매출총이익률</small></li>
            <li><span>매출총이익률이 바뀐 효과</span><Num f={formatWonCardDelta(b.margin)} /><small>원가율이 좋아지면 +, 나빠지면 −</small></li>
            <li><span>판관비가 바뀐 효과</span><Num f={formatWonCardDelta(b.sga)} /><small>판관비가 늘면 −</small></li>
            {Math.abs(b.other) >= 1e8 && <li><span>기타 영업손익</span><Num f={formatWonCardDelta(b.other)} /><small /></li>}
          </ul>
        </div>
      )}

      <Why />

      <YearTable title="이익률 단계별 추이" unit="매출 대비 %" years={years}
        rows={MARGINS.map((m) => ({ label: m.name, cells: years.map((yr) => formatPercent(inc[String(yr)].margins[m.key])) }))} />
      <LineGroupChart data={chartData} series={MARGINS.map((m) => ({ key: m.key, name: m.name }))} unit="%" />

      <p className={styles.footnote}>
        DART 재무제표(손익계산서) 값을 코드가 계산했습니다. 매출 대비 %는 공통형 손익계산서 방식(각 단계 ÷ 매출액)입니다.
        {derived.length > 0 && <> 공시에 따로 없는 단계는 계산으로 채웠습니다: {derived.join(', ')}.</>}
        {' '}영업외손익 = 세전이익 − 영업이익이며, 그중 금융손익을 뺀 나머지를 '기타'로 묶었습니다.
      </p>
    </SectionCard>
  )
}

// ───────── 왜 이렇게 됐나: 단계마다 AI 설명(근거 자료 표시) + 그 근거가 된 숫자(제품별 매출·주석 내역, 코드)
const WHY: { key: 'revenue' | 'gross' | 'sga' | 'non_operating' | 'tax'; title: string }[] = [
  { key: 'revenue', title: '매출은 왜 바뀌었나' },
  { key: 'gross', title: '매출총이익률(원가율)은 왜 바뀌었나' },
  { key: 'sga', title: '판매비와관리비는 왜 바뀌었나' },
  { key: 'non_operating', title: '영업외손익은 왜 바뀌었나 (금융손익·외환·처분손익)' },
  { key: 'tax', title: '법인세' },
]

function Why() {
  const ex = useContent('explain_income')
  const notes = useContent('income_notes')
  const seg = useContent('extract_segments')
  const web = useContent('web_news')
  if (!ex && !notes) return null
  return (
    <div className={styles.part}>
      <div className={styles.parttitle}>왜 이렇게 됐나 — 단계별 원인</div>
      {WHY.map(({ key, title }) => {
        const st = ex?.steps[key]
        const table = key === 'revenue' && seg ? <SegmentRows rows={seg.products} />
          : key === 'sga' && notes?.sga ? <NoteTable rows={notes.sga.rows} title={notes.sga.title} />
          : key === 'non_operating' ? <>{notes?.finance && <NoteTable rows={notes.finance.rows} title={notes.finance.title} />}
              {notes?.other && <NoteTable rows={notes.other.rows} title={notes.other.title} />}</>
          : null
        const news = (web?.items ?? []).filter((n) => n.step === key)
        if (!st && !table && news.length === 0) return null
        return (
          <div key={key} className={styles.whyblock}>
            <b>{title}</b>
            {st && <div>
              <AnalysisPoints text={st.text} />
              <p className={styles.analysisMeta}><AiBadge task="explain_income" />
                {st.basis.length > 0 && <> 근거: {st.basis.map((b) => ex?.sources[b] ?? b).join(', ')}</>}</p>
            </div>}
            {news.length > 0 && (
              <div className={styles.newsbox}>
                <span className={styles.newslabel}>기사에서 찾은 외부 요인</span> <AiBadge task="web_news" />
                <ul>
                  {news.map((n) => (
                    <li key={n.url}>{n.claim}{' '}
                      <a href={n.url} target="_blank" rel="noreferrer">{n.publisher || '기사'}{n.date ? ` · ${n.date}` : ''} ↗</a>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {table}
          </div>
        )
      })}
      <p className={styles.footnote}>
        설명은 AI가 아래 자료(제품별 매출, 사업보고서 주석의 판관비·금융손익·기타영업외손익 내역, 경영진의 설명)만 보고 썼고,
        자료에 없는 숫자가 든 문장은 버렸습니다. 표의 숫자는 사업보고서 주석을 코드가 읽어 계산한 값입니다. 회사 설명은 회사의 주장입니다.
        {web && web.items.length > 0 && <> '기사에서 찾은 외부 요인'은 AI가 웹 검색(최대 3번)으로 찾은 기사를 요약한 것이며, 실제로 검색된 기사 주소만 남겼습니다. 기사 속 숫자는 이 리포트가 검증하지 않았으니 원문 링크에서 확인하세요.</>}
      </p>
    </div>
  )
}

const TOP = 6

function NoteTable({ rows, title }: { rows: NoteRow[]; title: string }) {
  const totals = rows.filter((r) => r.is_total && r.change !== null)
  const items = rows.filter((r) => !r.is_total && r.change !== null && r.change !== 0)
    .sort((a, b) => Math.abs(b.change ?? 0) - Math.abs(a.change ?? 0)).slice(0, TOP)
  return (
    <div className={styles.tablescroll}>
      <p className={styles.sub}>{title.replace(/^\d+\.\s*/, '')} — 증감이 큰 항목 {items.length}개 (단위: 억 원)</p>
      <table className={styles.table}>
        <thead><tr><th>항목</th><th>전년</th><th>올해</th><th>증감</th></tr></thead>
        <tbody>
          {items.map((r) => (
            <tr key={`${r.group}-${r.item}`}><td>{r.group && r.group !== '합계' ? <span className={styles.sub}>{r.group} · </span> : null}{r.item}</td>
              <td><Num f={formatWonTable(r.prior)} /></td><td><Num f={formatWonTable(r.current)} /></td><td><Num f={formatWonTableDelta(r.change)} /></td></tr>
          ))}
          {totals.map((r) => (
            <tr key={`t-${r.group}-${r.item}`} className={styles.incstrong}><td>{r.item}</td>
              <td><Num f={formatWonTable(r.prior)} /></td><td><Num f={formatWonTable(r.current)} /></td><td><Num f={formatWonTableDelta(r.change)} /></td></tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function SegmentRows({ rows }: { rows: { name: string; current_won: number; prior_won: number | null; growth: number | null }[] }) {
  return (
    <div className={styles.tablescroll}>
      <table className={styles.table}>
        <thead><tr><th>제품·부문</th><th>전년</th><th>올해</th><th>증감</th><th>전년 대비</th></tr></thead>
        <tbody>
          {rows.map((p) => (
            <tr key={p.name}><td>{p.name}</td><td><Num f={formatWonTable(p.prior_won)} /></td><td><Num f={formatWonTable(p.current_won)} /></td>
              <td><Num f={formatWonTableDelta(p.prior_won === null ? null : p.current_won - p.prior_won)} /></td><td><Num f={formatChange(p.growth)} /></td></tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
