import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ApiError, getReport } from '../api'
import type { ReportDetail } from '../api'
import styles from '../app.module.css'
import { Cashflow, Competitors, CoreCards, Dupont, Header, RecentBox, Ratios, Sources, Trend } from '../report/sections'

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
    <>
      <Header r={report} />
      <div className={styles.pagebreak}>1페이지 · 한눈에 보기</div>
      <CoreCards r={report} />
      <div className={styles.pagebreak}>2페이지 · 재무 건전성</div>
      <RecentBox r={report} />
      <Trend r={report} />
      <Ratios r={report} />
      <Dupont r={report} />
      <Cashflow r={report} />
      <Competitors r={report} />
      <Sources r={report} />
    </>
  )
}
