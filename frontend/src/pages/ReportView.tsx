import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ApiError, getReport } from '../api'
import type { ReportDetail } from '../api'
import styles from '../app.module.css'
import { Accounting } from '../report/accounting'
import { AiBanner, AiProvider } from '../report/ai'
import { CommentsProvider } from '../report/comments'
import { FiveForces, Page4, Pest, Swot, Topics, Watch } from '../report/external'
import { Articles, Cashflow, Competitors, CoreCards, Dupont, Header, Macro, Overview, RecentBox, Ratios, Segments, Sources, Stocks, Trend } from '../report/sections'

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
      <Header r={report} />
      <AiBanner />
      <div className={styles.pagebreak}>1페이지 · 한눈에 보기</div>
      <Overview r={report} />
      <CoreCards r={report} />
      <Swot />
      <Segments r={report} />
      <div className={styles.pagebreak}>2페이지 · 재무 건전성</div>
      <RecentBox r={report} />
      <Trend r={report} />
      <Ratios r={report} />
      <Dupont r={report} />
      <Cashflow r={report} />
      <Accounting r={report} />
      <Competitors r={report} />
      <Stocks r={report} />
      <div className={styles.pagebreak}>3페이지 · 외부 환경과 관심사항</div>
      <Pest />
      <FiveForces />
      <Topics />
      <Macro r={report} />
      <Watch />
      <Articles r={report} />
      <div className={styles.pagebreak}>4페이지 · 회사의 과제와 나의 기여</div>
      <Page4 />
      <Sources r={report} />
     </AiProvider>
    </CommentsProvider>
  )
}
