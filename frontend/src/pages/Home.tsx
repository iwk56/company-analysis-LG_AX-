import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiError, createReport, getAiMode, identifyPdf, searchCompanies, setAiMode } from '../api'
import type { AiMode, PdfSlot, PdfUploadResult, SearchItem, SearchResult } from '../api'
import styles from '../app.module.css'
import { CompanyLogo } from '../ui/CompanyLogo'
import h from './home.module.css'

const MIN_QUERY_LENGTH = 2

interface Chip {
  name: string
  state: 'waiting' | 'reading' | 'done' | 'error'
  note?: string
}

// 처음 화면 (2026-11-03): 입력창 하나로 시작한다.
// + 버튼·끌어다 놓기 = 사업보고서 PDF (표지·종목코드로 기업을 찾고 사업보고서 칸 확인까지), 글자 입력 = 기업 이름 검색
export default function Home() {
  const navigate = useNavigate()
  const fileRef = useRef<HTMLInputElement>(null)
  const [query, setQuery] = useState('')
  const [reading, setReading] = useState<string | null>(null) // 읽는 중인 PDF 이름
  const [chips, setChips] = useState<Chip[]>([]) // 입력창 안에 보이는 올린 파일들
  const [searching, setSearching] = useState(false)
  const [result, setResult] = useState<SearchResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)
  const [creating, setCreating] = useState(false)
  const [aiMode, setAiModeState] = useState<AiMode | null>(null)
  const [aiModeError, setAiModeError] = useState<string | null>(null)
  const [aiModeUpdating, setAiModeUpdating] = useState(false)
  const busy = reading !== null || searching || creating

  useEffect(() => {
    let stale = false
    getAiMode()
      .then((mode) => !stale && setAiModeState(mode))
      .catch((e: ApiError) => !stale && setAiModeError(e.message))
    return () => {
      stale = true
    }
  }, [])

  async function toggleAiMode() {
    if (!aiMode || aiModeUpdating) return
    const enabled = !aiMode.live
    if (enabled && !window.confirm('실제 AI 호출을 켜면 새 리포트 생성이나 실패 작업 재시도에서 API 비용이 발생할 수 있습니다. 기존 리포트는 자동 재시도되지 않습니다. 켤까요?')) {
      return
    }
    setAiModeUpdating(true)
    setAiModeError(null)
    try {
      setAiModeState(await setAiMode(enabled))
    } catch (e) {
      setAiModeError((e as ApiError).message)
    } finally {
      setAiModeUpdating(false)
    }
  }

  // PDF를 1~2개 받는다 (사업보고서·반기/3분기 어느 쪽이든, 순서 상관없이). 하나씩 읽고 종류에 맞는 칸에 넣는다.
  // 진행 상태는 입력창 안의 파일 칩에 보인다 (2026-11-03)
  async function sendPdfs(list: FileList | null | undefined) {
    const files = Array.from(list ?? []).slice(0, 2)
    if (files.length === 0 || busy) return
    if (files.some((f) => !f.name.toLowerCase().endsWith('.pdf'))) {
      setError('PDF 파일만 올릴 수 있습니다')
      return
    }
    setError(null)
    setResult(null)
    const mark = (i: number, chip: Partial<Chip>) => setChips((cs) => cs.map((c, j) => (j === i ? { ...c, ...chip } : c)))
    setChips(files.map((f) => ({ name: f.name, state: 'waiting' })))
    let company: SearchItem | null = null
    const uploads: Partial<Record<PdfSlot, PdfUploadResult>> = {}
    for (const [i, file] of files.entries()) {
      setReading(file.name)
      mark(i, { state: 'reading' })
      try {
        const r = await identifyPdf(file)
        if (company && r.company.corp_code !== company.corp_code) {
          mark(i, { state: 'error', note: `${company.corp_name}와 다른 회사(${r.company.corp_name})의 보고서입니다` })
          setReading(null)
          return
        }
        company = r.company
        uploads[r.slot] = r.upload
        mark(i, r.upload.accepted
          ? { state: 'done', note: `${r.company.corp_name} · ${r.slot === 'annual' ? '사업보고서' : '반기/3분기보고서'}` }
          : { state: 'error', note: r.upload.reasons[0] ?? '확인을 통과하지 못했습니다' })
      } catch (e) {
        mark(i, { state: 'error', note: (e as ApiError).message })
        setReading(null)
        return
      }
    }
    setReading(null)
    if (!company) return
    // 사업보고서가 확인되고 거절된 파일이 없으면 확인 화면 없이 바로 리포트를 만든다 (2026-11-03)
    const annualId = uploads.annual?.accepted ? uploads.annual.upload_id : null
    const allAccepted = Object.values(uploads).every((u) => u?.accepted)
    if (annualId && allAccepted) {
      setCreating(true)
      try {
        const job = await createReport(company.corp_code, {
          annual: annualId,
          interim: uploads.interim?.upload_id ?? null,
        })
        navigate(`/jobs/${job.job_id}`)
        return
      } catch (e) {
        setError((e as ApiError).message)
        setCreating(false)
        return
      }
    }
    // 사업보고서가 없거나 거절된 파일이 있으면 이유를 보여 주는 PDF 화면으로 (그 칸만 다시 올리면 된다)
    navigate('/upload-reports', { state: { company, uploads } })
  }

  async function search(name?: string) {
    const q = (name ?? query).trim()
    setResult(null)
    if (q.length < MIN_QUERY_LENGTH) {
      setError('기업 이름은 2글자 이상 입력해 주세요')
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
    if (company.is_financial) {
      setError('현재 버전은 일반기업만 분석합니다') // 금융업은 선택해도 진행하지 않는다 (spec F1)
      return
    }
    // 2026-11-04: 기업만 고르면 바로 만든다. 보고서 글은 서버가 DART 공시 원문에서 자동으로 받는다
    setError(null)
    setCreating(true)
    createReport(company.corp_code, { annual: null })
      .then((job) => navigate(`/jobs/${job.job_id}`))
      .catch((e: ApiError) => {
        setError(e.message)
        setCreating(false)
      })
  }

  return (
    <div className={h.hero}>
      <h1 className={h.title}>어떤 회사를 분석할까요?</h1>
      <p className={h.lead}>기업 이름을 입력하면 DART 공시·사업보고서·뉴스를 자동으로 모아 리포트를 만들어요.</p>
      <section className={h.aiMode} aria-label="실제 AI 사용 설정">
        <div>
          <b>실제 AI 해석</b>
          <p className={h.aiModeHelp}>
            {aiMode?.live
              ? '켜짐 · 새 리포트와 재시도에서 API 비용이 발생할 수 있습니다.'
              : '꺼짐 · 켜면 새 리포트와 재시도에서 실제 AI를 호출합니다.'}
            {' '}리포트를 열기만 해서는 호출하지 않습니다.
          </p>
          {aiMode?.live && <p className={h.aiModeHelp}>끄면 이후 호출을 막습니다. 이미 진행 중인 요청은 취소되지 않습니다.</p>}
          {aiMode && aiMode.provider !== 'openai' && (
            <p className={h.aiModeHelp}>현재 제공자({aiMode.provider})에서는 이 설정을 사용할 수 없습니다.</p>
          )}
          {aiModeError && <p className={styles.error}>{aiModeError}</p>}
        </div>
        <button
          type="button"
          className={h.aiModeButton}
          aria-pressed={aiMode?.live ?? false}
          disabled={!aiMode || aiModeUpdating || aiMode.provider !== 'openai'}
          onClick={() => void toggleAiMode()}
        >
          {aiModeUpdating ? '변경 중…' : aiMode?.live ? '실제 AI 끄기' : '실제 AI 켜기'}
        </button>
      </section>

      <form
        className={`${h.composer} ${dragging ? h.dragging : ''}`}
        onSubmit={(e) => {
          e.preventDefault()
          void search()
        }}
        onDragOver={(e) => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDragging(false)
          void sendPdfs(e.dataTransfer.files)
        }}
      >
        {chips.length > 0 && (
          <div className={h.chips}>
            {chips.map((c) => (
              <div key={c.name} className={`${h.file} ${c.state === 'error' ? h.fileerror : ''}`}>
                <span className={h.fileicon}>PDF</span>
                <span className={h.filetext}>
                  <span className={h.filename}>{c.name}</span>
                  <span className={h.filenote}>
                    {c.state === 'waiting' && '기다리는 중'}
                    {c.state === 'reading' && <><span className={h.spinner} /> 읽고 확인하는 중… (10~20초)</>}
                    {c.state === 'done' && <>✓ {c.note}</>}
                    {c.state === 'error' && <>✗ {c.note}</>}
                  </span>
                </span>
                {!busy && (
                  <button type="button" className={h.fileclose} aria-label="지우기" onClick={() => setChips((cs) => cs.filter((x) => x !== c))}>×</button>
                )}
              </div>
            ))}
          </div>
        )}
        <div className={h.line}>
        <button
          type="button"
          className={h.attach}
          title="(선택) 사업보고서 PDF로 만들기"
          aria-label="보고서 PDF 올리기"
          disabled={busy}
          onClick={() => fileRef.current?.click()}
        >
          +
        </button>
        <input
          ref={fileRef}
          type="file"
          accept="application/pdf,.pdf"
          multiple
          hidden
          onChange={(e) => {
            void sendPdfs(e.target.files)
            e.target.value = '' // 같은 파일을 다시 골라도 다시 확인한다
          }}
        />
        <input
          className={h.input}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={dragging ? '여기에 PDF를 놓으세요' : chips.length > 0 ? '' : '기업 이름을 입력하세요 (예: SK하이닉스)'}
          aria-label="기업명"
          disabled={reading !== null || creating}
        />
        <button type="submit" className={h.send} aria-label="검색" disabled={busy || query.trim().length === 0}>
          ↑
        </button>
        </div>
        {creating && <div className={h.inner}><span className={h.spinner} /> 리포트 만들기 시작…</div>}
      </form>

      <div className={h.status}>
        {searching && (
          <span className={h.chip}>
            <span className={h.spinner} /> 검색 중…
          </span>
        )}
        {error && <p className={styles.error}>{error}</p>}
      </div>

      {result && (
        <div className={h.results}>
          {result.warning && <p className={styles.notice}>{result.warning}</p>}
          {result.message && <p className={styles.muted}>{result.message}</p>}
          {result.items.length > 0 && (
            <ul className={styles.results} style={{ marginTop: 0 }}>
              {result.items.map((c) => (
                <li key={c.corp_code} className={c.is_financial ? styles.disabled : undefined}>
                  <span className={h.company}>
                    <CompanyLogo name={c.corp_name} homepage={c.homepage} />
                    <span className={h.companytext}>
                      <b>{c.corp_name}</b> <span className={styles.sub}>{c.stock_code} · {c.industry_label}</span>
                      {c.is_financial && <span className={styles.error}>금융업은 리포트를 만들 수 없습니다</span>}
                    </span>
                  </span>
                  <button className={styles.primary} disabled={creating} onClick={() => pick(c)}>
                    리포트 만들기
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {!result && !reading && !creating && (
        <div className={h.hints}>
          {['SK하이닉스', 'LG전자', '삼성전자'].map((name) => (
            <button key={name} type="button" className={h.hint} onClick={() => {
                setQuery(name)
                void search(name)
              }}>
              {name}
            </button>
          ))}
        </div>
      )}

      <p className={h.foot}>사업보고서는 DART 공시 원문을 자동으로 읽어요. 가지고 있는 사업보고서 PDF로 만들고 싶으면 + 로 올려도 돼요.</p>
    </div>
  )
}
