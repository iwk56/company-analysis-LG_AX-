// "한눈에" 탭 (2026-11-04): 그림으로 회사를 파악하는 대시보드 + 탭별 한 줄 요약.
// 새 AI 호출 없이 이미 만든 결과(코드 계산·AI 추출)만 쓴다. 칸마다 [자세히 →]를 누르면 그 탭으로 간다.
// 네이버 기사는 약관(가공·일부만 골라 보여 주기 금지)상 여기 옮기지 않고 건수와 링크만 둔다.
import type { ReactNode } from 'react'
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { ChecklistItem, ReportDetail } from '../api'
import styles from '../app.module.css'
import { useContent } from './aiData'
import { CashflowChart, SegmentChart, StockIndexChart, TrendChart } from './charts'
import { COLORS } from './palette'
import { cashflowData, stockRows, trendData } from './sections'
import { useGoTab } from './tabs'
import type { TabKey } from './tabs'

function Tile({ title, tab, sub, children }: { title: string; tab: TabKey; sub?: ReactNode; children: ReactNode }) {
  const go = useGoTab()
  return (
    <div className={styles.tile}>
      <div className={styles.tilehead}>
        <span className={styles.tiletitle}>{title}</span>
        <button type="button" className={styles.link} onClick={() => go(tab)}>자세히 →</button>
      </div>
      {sub && <div className={styles.footnote}>{sub}</div>}
      {children}
    </div>
  )
}

const STATUS: Record<ChecklistItem['status'], { label: string; cls: string }> = {
  check: { label: '확인 필요', cls: styles.chipwarn },
  clear: { label: '이상 없음', cls: styles.chipgood },
  info: { label: '참고', cls: styles.chipinfo },
  unknown: { label: '확인 불가', cls: styles.chipinfo },
}

const EOK = 1e8

export function Glance({ r }: { r: ReportDetail }) {
  const seg = useContent('extract_segments')
  const check = useContent('checklist')
  const none = <p className={styles.muted}>자료 없음</p>

  const trend = trendData(r)
  const cash = cashflowData(r)
  const target = (r.stocks ?? []).filter((s) => s.is_target && s.points.length > 0)
  const rr = r.recent_results
  const recentBars = rr ? [
    { name: '매출액', prior: (rr.prior.revenue ?? 0) / EOK, current: (rr.current.revenue ?? 0) / EOK },
    { name: '영업이익', prior: (rr.prior.operating_income ?? 0) / EOK, current: (rr.current.operating_income ?? 0) / EOK },
    { name: '순이익', prior: (rr.prior.net_income ?? 0) / EOK, current: (rr.current.net_income ?? 0) / EOK },
  ] : []
  return (
    <section className={styles.card} data-section="glance">
      <div className={styles.tiles}>
        <Tile title="매출과 영업이익률 (5년)" tab="earnings" sub="막대: 매출액(억 원) · 선: 영업이익률">
          {trend.length ? <TrendChart data={trend} /> : none}
        </Tile>

        <Tile title={rr ? `최근 실적 (${rr.period_current} vs ${rr.period_prior})` : '최근 실적'} tab="earnings" sub="억 원, 누적 기준 전년 같은 기간과 비교">
          {rr ? (
            <div className={styles.chartbox}>
              <ResponsiveContainer>
                <BarChart data={recentBars} margin={{ top: 8, right: 8, left: 8, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="name" />
                  <YAxis tickFormatter={(v: number) => v.toLocaleString()} width={80} />
                  <Tooltip formatter={(v) => `${Math.round(Number(v)).toLocaleString()}억 원`} />
                  <Legend />
                  <Bar dataKey="prior" name={rr.period_prior} fill="#c3cad6" />
                  <Bar dataKey="current" name={rr.period_current} fill={COLORS[0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : none}
        </Tile>

        <Tile title="사업부문별 매출 비중" tab="business" sub={seg ? `${seg.year} 사업연도` : undefined}>
          {seg && seg.products.length ? <SegmentChart data={seg.products.map((p) => ({ name: p.name, share: (p.share ?? 0) * 100 }))} /> : none}
        </Tile>

        <Tile title="현금흐름 (5년)" tab="cashflow" sub="억 원 · 영업·투자·재무활동">
          {cash.length ? <CashflowChart data={cash} /> : none}
        </Tile>

        <Tile title="주가 (최근 1년)" tab="value" sub="기준일 종가 = 100">
          {target.length ? <StockIndexChart data={stockRows(target)} lines={target.map((s) => ({ key: s.corp_code, name: s.corp_name, isTarget: true }))} /> : none}
        </Tile>

        <Tile title="주의해서 볼 것" tab="outlook" sub={check ? `${check.base_year} 사업연도 기준 · 코드가 판정` : undefined}>
          {!check ? none : (
            <ul className={styles.chiplist}>
              {check.items.map((it) => (
                <li key={it.key}>
                  <span className={`${styles.chip} ${STATUS[it.status].cls}`}>{STATUS[it.status].label}</span>
                  <span className={styles.chiplabel}>{it.label}</span>
                </li>
              ))}
            </ul>
          )}
        </Tile>
      </div>

    </section>
  )
}
