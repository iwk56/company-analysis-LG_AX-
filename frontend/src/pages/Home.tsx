import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ApiError, listReports, searchCompanies } from '../api'
import type { ReportSummary, SearchItem, SearchResult } from '../api'
import styles from '../app.module.css'
import { dateText } from '../format/date'

const MIN_QUERY_LENGTH = 2
const RECENT_COUNT = 5

export default function Home() {
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [searching, setSearching] = useState(false)
  const [result, setResult] = useState<SearchResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [recent, setRecent] = useState<ReportSummary[] | null>(null)
  const [recentError, setRecentError] = useState<string | null>(null)

  useEffect(() => {
    listReports()
      .then((r) => setRecent(r.items.slice(0, RECENT_COUNT)))
      .catch((e: ApiError) => setRecentError(e.message))
  }, [])

  async function search() {
    const q = query.trim()
    setResult(null)
    if (q.length < MIN_QUERY_LENGTH) {
      setError('2글자 이상 입력해 주세요')
      return
    }
    setError(null)
    setSearching(true)
    try {
      setResult(await searchCompanies(q))
    } catch (e) {
      setError((e as ApiError).message)
    } finally {
      setSearching(false)
    }
  }

  function pick(company: SearchItem) {
    navigate('/select-competitors', { state: { company } }) // 다음 화면에서 경쟁사 1~4곳을 고른다
  }

  return (
    <>
      <section className={styles.card}>
        <h3>기업 검색</h3>
        <p className={styles.sub}>상장기업 이름을 2글자 이상 입력하세요 (금융업은 리포트를 만들 수 없습니다).</p>
        <form
          className={styles.row}
          onSubmit={(e) => {
            e.preventDefault()
            void search()
          }}
        >
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="예: SK하이닉스" aria-label="기업명" />
          <button className={styles.primary} type="submit" disabled={searching}>
            {searching ? '검색 중…' : '검색'}
          </button>
        </form>
        {error && <p className={styles.error}>{error}</p>}
        {result?.warning && <p className={styles.notice}>{result.warning}</p>}
        {result?.message && <p className={styles.notice}>{result.message}</p>}
        {result && result.items.length > 0 && (
          <ul className={styles.results}>
            {result.items.map((c) => (
              <li key={c.corp_code} className={c.is_financial ? styles.disabled : undefined}>
                <span>
                  <b>{c.corp_name}</b> <span className={styles.sub}>{c.stock_code} · {c.industry_label}</span>
                  {c.is_financial && <span className={styles.error}> · 금융업은 리포트를 만들 수 없습니다</span>}
                </span>
                <button
                  className={styles.primary}
                  disabled={c.is_financial}
                  onClick={() => pick(c)}
                >
                  경쟁사 선택
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className={styles.card}>
        <h3>최근 리포트</h3>
        {recentError && <p className={styles.error}>{recentError}</p>}
        {recent && recent.length === 0 && <p className={styles.muted}>아직 만든 리포트가 없습니다. 위에서 기업을 검색해 보세요.</p>}
        {recent && recent.length > 0 && (
          <ul className={styles.results}>
            {recent.map((r) => (
              <li key={r.id}>
                <span>
                  <Link to={`/reports/${r.id}`}><b>{r.corp_name}</b></Link>{' '}
                  <span className={styles.sub}>{dateText(r.created_at)} · {r.base_year}년 기준</span>
                </span>
              </li>
            ))}
          </ul>
        )}
        <p><Link to="/reports">전체 리포트 목록 →</Link></p>
      </section>
    </>
  )
}
