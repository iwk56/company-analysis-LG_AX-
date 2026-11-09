// 현금흐름 분석 (2026-11-04, 현금흐름 탭). 번 현금(영업)을 어디에 썼나(설비투자·주주환원·빚)와 '왜'를 보여 준다.
// 숫자는 백엔드 calc/cash.py가 DART 현금흐름표에서 계산한 값. 설명은 AI(explain_cashflow)가 그 숫자와 회사 설명만 보고 쓴 것.
import type { ReportDetail } from '../api'
import styles from '../app.module.css'
import { formatMultiple, formatPercent, formatWonCard, formatWonTable, formatWonTableDelta } from '../format/number'
import { Num } from '../ui'
import { AiBadge, AnalysisPoints } from './ai'
import { useContent } from './aiData'
import { SectionCard } from './comments'
import YearTable from './YearTable'

type M = Record<string, number | null>
interface CashItem { section: 'operating' | 'investing' | 'financing'; name: string; total: boolean; current: number | null; prior: number | null }
interface CashResult {
  years: Record<string, M>
  detail: { items: CashItem[] } | null
  bridge: { begin: number; end: number; steps: { label: string; amount: number }[]; unexplained?: number } | null
}

const ROWS: { key: string; label: string; kind: 'won' | 'x' | '%' }[] = [
  { key: 'cfo', label: '영업활동으로 번 현금', kind: 'won' },
  { key: 'capex', label: '설비투자 (유형·무형자산 취득)', kind: 'won' },
  { key: 'fcf', label: '잉여현금흐름 (영업 − 설비투자)', kind: 'won' },
  { key: 'shareholder_returns', label: '주주환원 (배당 + 자사주)', kind: 'won' },
  { key: 'net_borrowing', label: '차입금 순증감 (+빌림 / −갚음)', kind: 'won' },
  { key: 'tax_paid', label: '법인세 납부', kind: 'won' },
  { key: 'cash_end', label: '기말 현금', kind: 'won' },
  { key: 'cfo_to_net_income', label: '영업현금 ÷ 순이익 (이익의 질)', kind: 'x' },
  { key: 'capex_to_revenue', label: '설비투자 ÷ 매출', kind: '%' },
]

const WHY: { key: 'operating' | 'investing' | 'financing' | 'fcf'; title: string }[] = [
  { key: 'operating', title: '영업으로 번 현금은 왜 바뀌었나' },
  { key: 'investing', title: '투자에 얼마를 왜 썼나' },
  { key: 'financing', title: '주주환원·빚은 어떻게 했나' },
  { key: 'fcf', title: '잉여현금흐름과 기말 현금은 어떻게 다른가' },
]
const SECTION_OF = { operating: 'operating', investing: 'investing', financing: 'financing' } as const

function plainCashExplanation(text: string): string {
  return text
    .replaceAll('현금 다리에서는 이 현금의 흐름에 이어', '잉여현금흐름 외에도')
    .replaceAll('현금 다리의 기말 현금은', '연말 현금 잔액은')
    .replaceAll('현금 다리에', '연말 현금 계산에')
    .replaceAll('현금 다리는', '연초부터 연말까지의 현금 변동은')
    .replaceAll('현금 다리', '연초부터 연말까지의 현금 변동')
}

export function CashAnalysis({ r }: { r: ReportDetail }) {
  const cash = r.results.cash as CashResult | undefined
  const ex = useContent('explain_cashflow')
  if (!cash) return null
  const years = Object.keys(cash.years).map(Number).sort()
  const shown = ROWS.filter((row) => years.some((y) => cash.years[String(y)]?.[row.key] !== null && cash.years[String(y)]?.[row.key] !== undefined))
  const fmt = (v: number | null | undefined, kind: 'won' | 'x' | '%') => (kind === 'won' ? formatWonTable(v) : kind === 'x' ? formatMultiple(v) : formatPercent(v))
  const b = cash.bridge
  const max = b ? Math.max(...b.steps.map((s) => Math.abs(s.amount)), 1) : 1
  const investmentItems = (cash.detail?.items ?? [])
    .filter((item): item is CashItem & { current: number } => item.section === 'investing' && !item.total && item.current !== null && item.current !== 0
      && !/(?:유형|무형)자산.*취득|취득.*(?:유형|무형)자산/.test(item.name))
    .sort((a, z) => Math.abs(z.current ?? 0) - Math.abs(a.current ?? 0))
    .slice(0, 5)
  const bridgeCalculatedEnd = b && b.unexplained !== undefined ? b.end - b.unexplained : null
  const bridgeMatches = b && b.unexplained !== undefined
    ? Math.abs(b.unexplained) <= Math.max(1, Math.abs(b.end) * 1e-10)
    : null
  const latestMetrics = cash.years[String(r.base_year)]
  return (
    <SectionCard sectionKey="cash_analysis">
      <h3>현금흐름 분석 <span className={styles.unit}>(번 현금을 어디에 썼나)</span></h3>

      {b && (
        <div className={styles.part}>
          <div className={styles.parttitle}>기초 현금에서 기말 현금까지 ({r.base_year})</div>
          <table className={`${styles.table} ${styles.cashbridge}`}>
            <tbody>
              <tr className={styles.incstrong}><td>기초 현금</td><td><Num f={formatWonCard(b.begin)} /></td><td /></tr>
              {b.steps.filter((s) => Math.abs(s.amount) >= 1e8).map((s) => (
                <tr key={s.label}>
                  <td className={styles.incsub}>{s.amount >= 0 ? '(+)' : '(−)'} {s.label === '그 밖의 투자(금융상품·지분 등)' ? '설비투자 외 투자활동 순액' : s.label}</td>
                  <td><Num f={formatWonCard(s.amount)} /></td>
                  <td className={styles.left}><span className={s.amount >= 0 ? styles.barin : styles.barout} style={{ width: `${(Math.abs(s.amount) / max) * 100}%` }} /></td>
                </tr>
              ))}
              <tr className={styles.incstrong}><td>기말 현금</td><td><Num f={formatWonCard(b.end)} /></td><td /></tr>
            </tbody>
          </table>
          {investmentItems.length > 0 && (
            <div className={styles.cashDetail}>
              <b>설비투자 외 투자활동의 주요 세부 항목</b>
              <ul>
                {investmentItems.map((item) => (
                  <li key={item.name}>
                    <span>{item.name}</span>
                    <b><Num f={formatWonCard(item.current)} /></b>
                    <span className={styles.sub}>{item.current < 0 ? '현금 유출' : '현금 유입'}</span>
                  </li>
                ))}
              </ul>
              <p className={styles.footnote}>위는 금액이 큰 세부 항목 일부입니다. 설비투자 외 투자활동 순액은 여러 투자 거래를 합한 값이므로 비용·손실이나 현금이 사라졌다는 뜻은 아닙니다. 금융상품 취득은 현금이 금융자산으로 바뀐 거래일 수 있습니다.</p>
            </div>
          )}
          {bridgeMatches !== null && bridgeCalculatedEnd !== null && (
            <p className={bridgeMatches ? styles.cashCheck : styles.notice}>
              {bridgeMatches ? '대사 확인: ' : '대사 차이 확인 필요: '}
              기초 현금과 위 현금흐름으로 계산한 기말 현금 <Num f={formatWonCard(bridgeCalculatedEnd)} /> ·
              {' '}DART 기말 현금 <Num f={formatWonCard(b.end)} /> · 차이 <Num f={formatWonCard(b.unexplained)} />
            </p>
          )}
          <p className={styles.footnote}>DART 현금흐름표 값을 코드가 묶었습니다. 초록은 들어온 현금, 빨강은 나간 현금입니다.</p>
        </div>
      )}

      <YearTable title="핵심 현금 지표" unit="억 원 · 배 · %" years={years}
        rows={shown.map((row) => ({ label: row.label, cells: years.map((y) => fmt(cash.years[String(y)]?.[row.key], row.kind)) }))}
        footnote={<>{shown.length < 6 && '설비투자·배당·차입 등 세부 항목은 2026-11-04 이후 만든 리포트부터 나옵니다. '}영업현금 ÷ 순이익이 1배보다 크면 이익보다 현금이 더 들어온 것입니다. 지출 항목(설비투자·주주환원·법인세)은 나간 금액입니다.</>} />

      {(ex || cash.detail) && (
        <div className={styles.part}>
          <div className={styles.parttitle}>왜 이렇게 됐나 — 활동별 원인</div>
          {WHY.map(({ key, title }) => {
            const st = ex?.steps[key]
            const items = key === 'fcf' ? [] : (cash.detail?.items ?? []).filter((i) => i.section === SECTION_OF[key] && !i.total && i.current !== null && i.current !== 0)
              .sort((a, z) => Math.abs((z.current ?? 0) - (z.prior ?? 0)) - Math.abs((a.current ?? 0) - (a.prior ?? 0))).slice(0, 6)
            if (!st && items.length === 0) return null
            return (
              <div key={key} className={`${styles.whyblock} ${styles.cashWhyblock}`}>
                <b>{title}</b>
                {key === 'fcf' && latestMetrics && (
                  <div className={styles.cashFact}>
                    <p><b>코드 계산</b> 영업활동 현금흐름 <Num f={formatWonCard(latestMetrics.cfo)} /> − 설비투자 <Num f={formatWonCard(latestMetrics.capex)} /> = 잉여현금흐름 <Num f={formatWonCard(latestMetrics.fcf)} />입니다.</p>
                    <p>잉여현금흐름은 해당 기간 영업현금에서 설비투자를 뺀 값이지, 회사가 보유한 기말 현금 잔액이 아닙니다. 기말 현금은 기초 현금에 영업·투자·재무 현금흐름과 환율 효과를 모두 반영해 계산합니다.</p>
                    {b && <p>연초 현금 잔액은 <Num f={formatWonCard(b.begin)} />, 연말 현금 잔액은 <Num f={formatWonCard(b.end)} />입니다. {bridgeMatches ? '이 계산 결과는 DART 기말 현금과 일치합니다.' : '기초·기말 잔액과 현금흐름 자료를 확인해 주세요.'}</p>}
                  </div>
                )}
                {st && key !== 'fcf' && <div>
                  <AnalysisPoints text={plainCashExplanation(st.text)} />
                  <p className={styles.analysisMeta}><AiBadge task="explain_cashflow" />
                    {st.basis.length > 0 && <> 근거: {st.basis.map((k) => ex?.sources[k] ?? k).join(', ')}</>}</p>
                </div>}
                {items.length > 0 && (
                  <div className={styles.tablescroll}>
                    <table className={styles.table}>
                      <thead><tr><th>항목 (증감이 큰 순)</th><th>전년</th><th>올해</th><th>증감</th></tr></thead>
                      <tbody>
                        {items.map((i) => (
                          <tr key={i.name}><td>{i.name}</td><td><Num f={formatWonTable(i.prior)} /></td><td><Num f={formatWonTable(i.current)} /></td>
                            <td><Num f={formatWonTableDelta(i.prior === null || i.current === null ? null : i.current - i.prior)} /></td></tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )
          })}
          <p className={styles.footnote}>표는 DART 현금흐름표 세부 행(들어온 돈 +, 나간 돈 −, 단위 억 원). 설명은 AI가 이 숫자와 회사 설명만 보고 썼고, 자료에 없는 숫자가 든 문장은 버렸습니다.</p>
        </div>
      )}
    </SectionCard>
  )
}
