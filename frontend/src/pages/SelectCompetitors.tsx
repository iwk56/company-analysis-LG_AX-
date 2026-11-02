import { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { ApiError, createReport, searchCompanies } from '../api'
import type { SearchItem, SearchResult } from '../api'
import styles from '../app.module.css'

const MIN_QUERY_LENGTH = 2
const MAX_COMPETITORS = 4

export default function SelectCompetitors() {
  const navigate = useNavigate()
  const company = (useLocation().state as { company?: SearchItem } | null)?.company
  const [query, setQuery] = useState('')
  const [searching, setSearching] = useState(false)
  const [result, setResult] = useState<SearchResult | null>(null)
  const [selected, setSelected] = useState<SearchItem[]>([])
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)

  if (!company) {
    return (
      <section className={styles.card}>
        <p>분석할 기업이 정해지지 않았습니다. <Link to="/">홈에서 기업을 먼저 검색해 주세요.</Link></p>
      </section>
    )
  }

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

  function add(c: SearchItem) {
    if (selected.length >= MAX_COMPETITORS) {
      setNotice('최대 4곳까지 선택할 수 있습니다')
      return
    }
    setNotice(null)
    setSelected([...selected, c])
  }

  function remove(code: string) {
    setNotice(null)
    setSelected(selected.filter((c) => c.corp_code !== code))
  }

  async function create() {
    if (!company) return
    setCreating(true)
    setError(null)
    try {
      const job = await createReport(company.corp_code, selected.map((c) => c.corp_code))
      navigate(`/jobs/${job.job_id}`)
    } catch (e) {
      setError((e as ApiError).message)
      setCreating(false)
    }
  }

  return (
    <>
      <section className={styles.card}>
        <h3>경쟁사 선택 — {company.corp_name} 분석</h3>
        <p className={styles.sub}>
          비교할 상장기업을 기업명으로 검색해 1~4곳 추가하세요 (금융업은 추가할 수 없습니다).
        </p>
        <form
          className={styles.row}
          onSubmit={(e) => {
            e.preventDefault()
            void search()
          }}
        >
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="예: 삼성전자" aria-label="경쟁사 이름" />
          <button className={styles.primary} type="submit" disabled={searching}>
            {searching ? '검색 중…' : '검색'}
          </button>
        </form>
        {result?.warning && <p className={styles.notice}>{result.warning}</p>}
        {result?.message && <p className={styles.notice}>{result.message}</p>}
        {result && result.items.length > 0 && (
          <ul className={styles.results}>
            {result.items.map((c) => {
              const isSelf = c.corp_code === company.corp_code
              const picked = selected.some((s) => s.corp_code === c.corp_code)
              const blocked = c.is_financial || isSelf || picked
              return (
                <li key={c.corp_code} className={blocked ? styles.disabled : undefined}>
                  <span>
                    <b>{c.corp_name}</b> <span className={styles.sub}>{c.stock_code} · {c.industry_label}</span>
                    {c.is_financial && <span className={styles.error}> · 금융업은 추가할 수 없습니다</span>}
                    {isSelf && <span className={styles.sub}> · 분석 기업</span>}
                    {picked && <span className={styles.sub}> · 선택됨</span>}
                  </span>
                  <button className={styles.primary} disabled={blocked} onClick={() => add(c)}>추가</button>
                </li>
              )
            })}
          </ul>
        )}
      </section>

      <section className={styles.card}>
        <h3>선택한 경쟁사 ({selected.length}/{MAX_COMPETITORS})</h3>
        {selected.length === 0 && <p className={styles.muted}>아직 선택한 경쟁사가 없습니다. 1곳 이상 추가해야 리포트를 만들 수 있습니다.</p>}
        {selected.length > 0 && (
          <ul className={styles.results}>
            {selected.map((c) => (
              <li key={c.corp_code}>
                <span><b>{c.corp_name}</b> <span className={styles.sub}>{c.stock_code} · {c.industry_label}</span></span>
                <button className={styles.danger} onClick={() => remove(c.corp_code)}>제외</button>
              </li>
            ))}
          </ul>
        )}
        {notice && <p className={styles.notice}>{notice}</p>}
        {error && <p className={styles.error}>{error}</p>}
        <p>
          <button className={styles.primary} disabled={selected.length === 0 || creating} onClick={() => void create()}>
            {creating ? '시작 중…' : '리포트 만들기'}
          </button>{' '}
          <Link to="/">취소</Link>
        </p>
      </section>
    </>
  )
}
