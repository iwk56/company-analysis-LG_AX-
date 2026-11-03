import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ApiError, getReport } from '../api'
import type { ReportDetail } from '../api'
import styles from '../app.module.css'
import { Accounting } from '../report/accounting'
import { AiBanner, AiProvider } from '../report/ai'
import { CommentsProvider } from '../report/comments'
import { FiveForces, Interview, Pest, RoleIdeas, Swot, Tasks, Topics, Verdict } from '../report/external'
import { Appendix, AppendixGroup, NavProvider } from '../report/fold'
import {
  Articles, Cashflow, Competitors, CoreCards, Dupont, EssayNumbers, Header, Macro, Overview, Position, RecentBox, Ratios, Segments, Sources, Stocks, Trend,
} from '../report/sections'

export default function ReportPage() {
  const { reportId = '' } = useParams()
  return <ReportView key={reportId} reportId={reportId} />
}

function ReportView({ reportId }: { reportId: string }) {
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
     <NavProvider>
      {/* 화면은 결론부터 1~4장 + 부록 (spec.md F4). 위치와 묶음만 바꾸고 데이터·AI 호출은 그대로 */}
      <div className={styles.pagebreak}>1장 · 회사 한눈에</div>
      {/* 1장 디자인(docs/design.md): 위는 대시보드(헤더·종합 한 줄 평가·핵심 지표), 아래는 번호 붙은 리포트 섹션 */}
      <div className={styles.p1}>
        <Header r={report} />
        <AiBanner />
        <Verdict />
        <CoreCards r={report} />
        <Overview r={report} />
        <Segments r={report} />
        <Position r={report} />
      </div>
      <div className={styles.pagebreak}>2장 · 지금 회사의 이슈</div>
      <RecentBox r={report} />
      <Topics />
      <Articles r={report} />
      <div className={styles.pagebreak}>3장 · 강점과 과제</div>
      <Swot />
      <Tasks />
      <div className={styles.pagebreak}>4장 · 나와의 연결</div>
      <RoleIdeas />
      <Interview />
      <EssayNumbers r={report} />
      <div className={styles.pagebreak}>부록 · 심화 분석</div>
      <Appendix>
        <AppendixGroup title="A. 거시" />
        <Pest />
        <Macro r={report} />
        <AppendixGroup title="B. 산업" />
        <FiveForces />
        <AppendixGroup title="C. 재무" />
        <Trend r={report} />
        <Ratios r={report} />
        <Dupont r={report} />
        <Cashflow r={report} />
        <Accounting r={report} />
        <AppendixGroup title="D. 가치평가" />
        <Stocks r={report} />
        <AppendixGroup title="E. 경쟁사 비교" />
        <Competitors r={report} />
      </Appendix>
      <Sources r={report} />
     </NavProvider>
     </AiProvider>
    </CommentsProvider>
  )
}
