import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError, deleteReport, listReports } from '../api'
import type { ReportSummary } from '../api'
import styles from '../app.module.css'
import { dateText } from '../format/date'

export default function ReportList() {
  const [q, setQ] = useState('')
  const [applied, setApplied] = useState('')
  const [items, setItems] = useState<ReportSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let stale = false
    listReports(applied)
      .then((r) => {
        if (!stale) {
          setItems(r.items)
          setError(null)
        }
      })
      .catch((e: ApiError) => !stale && setError(e.message))
    return () => {
      stale = true
    }
  }, [applied])

  async function remove(r: ReportSummary) {
    if (!window.confirm(`${r.corp_name} (${dateText(r.created_at)}) 리포트를 삭제할까요?\n삭제하면 되돌릴 수 없습니다.`)) return
    try {
      await deleteReport(r.id)
      setItems((cur) => cur && cur.filter((x) => x.id !== r.id))
    } catch (e) {
      setError((e as ApiError).message)
    }
  }

  return (
    <section className={styles.card}>
      <h3>리포트 목록</h3>
      <form
        className={styles.row}
        onSubmit={(e) => {
          e.preventDefault()
          setApplied(q.trim())
        }}
      >
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="기업명 일부" aria-label="기업명 필터" />
        <button className={styles.primary} type="submit">검색</button>
      </form>
      {error && <p className={styles.error}>{error}</p>}
      {items && items.length === 0 && (
        <p className={styles.muted}>{applied ? '일치하는 리포트가 없습니다.' : '아직 만든 리포트가 없습니다.'}</p>
      )}
      {items && items.length > 0 && (
        <table className={styles.table}>
          <thead>
            <tr><th>기업명</th><th>생성일</th><th>기준 사업연도</th><th>경쟁사 수</th><th /></tr>
          </thead>
          <tbody>
            {items.map((r) => (
              <tr key={r.id}>
                <td><Link to={`/reports/${r.id}`}>{r.corp_name}</Link></td>
                <td>{dateText(r.created_at)}</td>
                <td>{r.base_year}</td>
                <td>{r.competitor_count}</td>
                <td><button className={styles.danger} onClick={() => void remove(r)}>삭제</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}
