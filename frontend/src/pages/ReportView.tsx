import { useCallback, useEffect, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { ApiError, getReport } from '../api'
import type { ReportDetail } from '../api'
import styles from '../app.module.css'
import { Accounting } from '../report/accounting'
import { AiBanner, AiProvider } from '../report/ai'
import { CommentsProvider } from '../report/comments'
import { IncomeStatement } from '../report/income'
import { CashAnalysis } from '../report/cash'
import { FiveForces, Pest, Swot, Verdict } from '../report/external'
import { Caution, Future, Industry, Interests, Mda } from '../report/jobseeker'
import { NavProvider } from '../report/fold'
import { BusinessStructure, PeerInsight, Subsidiaries } from '../report/business'
import { Glance } from '../report/glance'
import { SourcesTab } from '../report/sourcesTab'
import { SECTION_TAB, TABS, TabCtx, isTab } from '../report/tabs'
import type { TabKey } from '../report/tabs'
import {
  Articles, BalanceSummary, Cashflow, Competitors, CoreCards, Dupont, Header, Overview, RecentBox, Ratios, Segments, Stocks, Trend,
} from '../report/sections'

export default function ReportPage() {
  const { reportId = '' } = useParams()
  return <ReportView key={reportId} reportId={reportId} />
}

function ReportView({ reportId }: { reportId: string }) {
  const [params, setParams] = useSearchParams()
  const raw = params.get('tab')
  const tab: TabKey = isTab(raw) ? raw : 'summary'
  const go = useCallback((t: TabKey) => {
    setParams(t === 'summary' ? {} : { tab: t })
    window.scrollTo(0, 0)
  }, [setParams])
  const onJump = useCallback((key: string) => {
    const t = SECTION_TAB[key]
    if (t) setParams(t === 'summary' ? {} : { tab: t })
  }, [setParams])
  const [report, setReport] = useState<ReportDetail | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let stale = false
    getReport(Number(reportId))
      .then((r) => !stale && setReport(r))
      .catch((e: ApiError) => !stale && setError(e.message))
    return () => {
      stale = true
    }
  }, [reportId])

  if (error) return <p className={styles.error}>{error} <Link to="/reports">목록으로</Link></p>
  if (!report) return <p className={styles.muted}>불러오는 중…</p>
  return (
    <CommentsProvider reportId={report.id} initial={report.comments}>
     <AiProvider report={report}>
     <TabCtx.Provider value={go}>
     <NavProvider onJump={onJump}>
      {/* 2026-11-04 탭 구성: 헤더는 위에 고정, 아래는 한눈에 · 회사·업계 · 최근 소식 · 미래·전략 · 재무 데이터 · 주의할 점 · 출처 (11-04 일하는 환경 탭 없앰, 직원 현황은 회사·업계로).
          위치만 바꾸고 데이터·AI 호출은 그대로. "나는 뭘 쓰고 말하면 돼요?"(직무별 기여·면접 질문·숫자 모음)는 화면에서 뺀 상태 유지 */}
      <div className={styles.p1} data-tab={tab}>
        <Header r={report} />
        <AiBanner />
        <nav className={styles.tabs} aria-label="리포트 탭">
          {TABS.map((t) => (
            <button key={t.key} type="button" className={`${styles.tab} ${t.key === tab ? styles.tabon : ''}`}
              aria-current={t.key === tab ? 'page' : undefined} onClick={() => go(t.key)}>
              {t.label}
            </button>
          ))}
        </nav>

        {tab === 'summary' && (
          <>
            <Verdict />
            <CoreCards r={report} />
            <Glance r={report} />
          </>
        )}
        {tab === 'business' && (
          <>
            <Overview r={report} />
            <Segments r={report} />
            <BusinessStructure />
            <Subsidiaries />
          </>
        )}
        {tab === 'industry' && (
          <>
            <Industry />
            <Competitors r={report} />
            <PeerInsight />
            <FiveForces />
            <Pest />
            {/* 경제 환경 민감도(환율·기준금리) 부록: 최종 형태 확정 전까지 숨김 (2026-11-05) */}
          </>
        )}
        {tab === 'earnings' && (
          <>
            <RecentBox r={report} />
            <Trend r={report} />
            <IncomeStatement r={report} />
            <Ratios r={report} groups={['수익성', '성장성']} title="수익성·성장성 비율" sectionKey="profit_ratios" />
            <Mda />
            <Dupont r={report} />
          </>
        )}
        {tab === 'position' && (
          <>
            <BalanceSummary r={report} />
            <Ratios r={report} groups={['안정성', '활동성']} title="안정성·활동성 비율" />
          </>
        )}
        {tab === 'cashflow' && (
          <>
            <Cashflow r={report} />
            <CashAnalysis r={report} />
          </>
        )}
        {tab === 'value' && <Stocks r={report} />}
        {tab === 'news' && (
          <>
            <Articles r={report} />
            <Interests />
          </>
        )}
        {tab === 'outlook' && (
          <>
            <Future />
            <Swot />
            <Caution />
            <Accounting r={report} />
          </>
        )}
        {tab === 'sources' && <SourcesTab r={report} />}
      </div>
     </NavProvider>
     </TabCtx.Provider>
     </AiProvider>
    </CommentsProvider>
  )
}
