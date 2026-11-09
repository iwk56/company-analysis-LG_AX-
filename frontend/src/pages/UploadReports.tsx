import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { ApiError, createReport, getPdfGuide, uploadPdf } from '../api'
import type { PdfGuide, PdfGuideItem, PdfSlot, PdfUploadResult, SearchItem } from '../api'
import styles from '../app.module.css'

// 칸마다의 상태: 비어 있음 → 확인 중 → 확인 결과(통과·거절) 또는 요청 오류
type SlotState =
  | { status: 'empty' }
  | { status: 'checking'; fileName: string }
  | { status: 'done'; result: PdfUploadResult }
  | { status: 'error'; fileName: string; message: string }

const SLOT_TITLES: Record<PdfSlot, string> = { annual: '사업보고서 (필수)', interim: '반기 또는 3분기보고서 (선택)' }
const KIND_LABELS = { annual: '사업보고서', half: '반기보고서', q3: '3분기보고서', q1: '1분기보고서' }

export default function UploadReports() {
  const navigate = useNavigate()
  const state = useLocation().state as { company?: SearchItem; uploads?: Partial<Record<PdfSlot, PdfUploadResult>> } | null
  const company = state?.company
  const [guide, setGuide] = useState<PdfGuide | null>(null)
  const [guideError, setGuideError] = useState<string | null>(null)
  const [slots, setSlots] = useState<Record<PdfSlot, SlotState>>({
    // 처음 화면에서 올린 PDF가 있으면 그 확인 결과로 칸을 채워 시작한다
    annual: state?.uploads?.annual ? { status: 'done', result: state.uploads.annual } : { status: 'empty' },
    interim: state?.uploads?.interim ? { status: 'done', result: state.uploads.interim } : { status: 'empty' },
  })
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!company) return
    getPdfGuide(company.corp_code)
      .then(setGuide)
      .catch((e: ApiError) => setGuideError(e.message))
  }, [company])

  if (!company) {
    return (
      <section className={styles.card}>
        <p>분석할 기업이 정해지지 않았습니다. <Link to="/">처음 화면에서 보고서 PDF를 먼저 올려 주세요.</Link></p>
      </section>
    )
  }

  const uploadId = (slot: PdfSlot) => {
    const s = slots[slot]
    return s.status === 'done' && s.result.accepted ? s.result.upload_id : null
  }
  const busy = slots.annual.status === 'checking' || slots.interim.status === 'checking'
  const ready = uploadId('annual') !== null && !busy

  async function pick(slot: PdfSlot, file: File | undefined) {
    if (!company || !file) return
    setError(null)
    setSlots((s) => ({ ...s, [slot]: { status: 'checking', fileName: file.name } }))
    const other = uploadId(slot === 'annual' ? 'interim' : 'annual')
    try {
      const result = await uploadPdf(company.corp_code, slot, file, other)
      setSlots((s) => ({ ...s, [slot]: { status: 'done', result } }))
    } catch (e) {
      setSlots((s) => ({ ...s, [slot]: { status: 'error', fileName: file.name, message: (e as ApiError).message } }))
    }
  }

  function clear(slot: PdfSlot) {
    setSlots((s) => ({ ...s, [slot]: { status: 'empty' } }))
  }

  async function create() {
    if (!company) return
    setCreating(true)
    setError(null)
    try {
      const job = await createReport(company.corp_code, { annual: uploadId('annual'), interim: uploadId('interim') })
      navigate(`/jobs/${job.job_id}`)
    } catch (e) {
      setError((e as ApiError).message)
      setCreating(false)
    }
  }

  return (
    <>
      <section className={styles.card}>
        <h3>보고서 PDF 올리기 — {company.corp_name}</h3>
        <p className={styles.sub}>
          회사 설명·경영진단·연구개발 같은 서술 내용은 올린 PDF에서, 재무 숫자는 DART에서 가져옵니다.
        </p>
        {guideError && <p className={styles.error}>{guideError}</p>}
        {!guide && !guideError && <p className={styles.muted}>올릴 보고서를 DART 공시 목록에서 찾는 중…</p>}
        {guide && (
          <>
            {guide.message && <p className={styles.error}>{guide.message}</p>}
            <ul className={styles.itemlist}>
              <GuideLine label="① 사업보고서 (필수)" item={guide.annual} />
              <GuideLine
                label="② 반기/3분기보고서 (선택)"
                item={guide.interim}
                empty={guide.base_year ? `${guide.base_year + 1}년 반기·3분기보고서가 아직 제출되지 않았습니다` : '—'}
              />
            </ul>
            <p className={styles.sub}>
              링크를 눌러 DART 공시뷰어를 열고, 오른쪽 위 [다운로드]에서 PDF를 받아 아래 칸에 올리세요. 원본 파일은 저장하지 않고 읽은 글자만 저장합니다.
            </p>
          </>
        )}
      </section>

      {(['annual', 'interim'] as const).map((slot) => (
        <section key={slot} className={styles.card}>
          <h3>{SLOT_TITLES[slot]}</h3>
          <p>
            <input
              type="file"
              accept="application/pdf,.pdf"
              aria-label={SLOT_TITLES[slot]}
              disabled={busy || creating || !guide?.base_year}
              onChange={(e) => {
                void pick(slot, e.target.files?.[0])
                e.target.value = '' // 같은 파일을 다시 골라도 다시 확인한다
              }}
            />{' '}
            {slots[slot].status !== 'empty' && slots[slot].status !== 'checking' && (
              <button className={styles.danger} onClick={() => clear(slot)} disabled={creating}>지우기</button>
            )}
          </p>
          <SlotResult state={slots[slot]} />
        </section>
      ))}

      <section className={styles.card}>
        {error && <p className={styles.error}>{error}</p>}
        {!ready && !busy && <p className={styles.muted}>사업보고서 PDF가 확인되면 리포트를 만들 수 있습니다.</p>}
        <p>
          <button className={styles.primary} disabled={!ready || creating} onClick={() => void create()}>
            {creating ? '시작 중…' : '리포트 만들기'}
          </button>{' '}
          <Link to="/">취소</Link>
        </p>
      </section>
    </>
  )
}

function GuideLine({ label, item, empty }: { label: string; item: PdfGuideItem | null; empty?: string }) {
  return (
    <li>
      <b>{label}</b>:{' '}
      {item ? (
        <>
          {item.year} {KIND_LABELS[item.kind]} ({item.date} 제출) ·{' '}
          <a href={item.url} target="_blank" rel="noreferrer">공시뷰어에서 열기</a>
        </>
      ) : (
        <span className={styles.muted}>{empty ?? '찾지 못했습니다'}</span>
      )}
    </li>
  )
}

function SlotResult({ state }: { state: SlotState }) {
  if (state.status === 'empty') return <p className={styles.muted}>아직 올리지 않았습니다.</p>
  if (state.status === 'checking')
    return <p className={styles.muted}>{state.fileName} 확인 중… (400쪽 PDF는 10초쯤 걸립니다)</p>
  if (state.status === 'error')
    return (
      <p className={styles.bad}>
        다시 올려 주세요 ✗ — {state.fileName}: {state.message}
      </p>
    )
  const r = state.result
  if (!r.accepted)
    return (
      <>
        <p className={styles.bad}>다시 올려 주세요 ✗ — {r.file_name}</p>
        <ul className={styles.itemlist}>
          {r.reasons.map((x) => (
            <li key={x} className={styles.bad}>{x}</li>
          ))}
        </ul>
      </>
    )
  return (
    <>
      <p className={styles.good}>
        확인됨 ✓ — {r.file_name} ({r.page_count.toLocaleString()}쪽{r.kind ? `, ${KIND_LABELS[r.kind]}` : ''}
        {r.period_start && r.period_end ? `, ${r.period_start} ~ ${r.period_end}` : ''})
      </p>
      <ul className={styles.itemlist}>
        {r.checks.map((c) => (
          <li key={c.key} className={styles.sub}>
            {c.label}: {c.message}
          </li>
        ))}
      </ul>
      {r.corrected && <p className={styles.notice}>정정 보고서([기재정정])입니다.</p>}
      {r.revenue && r.revenue.status === 'match' && <p className={styles.sub}>{r.revenue.message}</p>}
      {r.revenue && r.revenue.status !== 'match' && (
        <p className={styles.notice}>{r.revenue.message} — 확인에는 문제가 없어 그대로 진행할 수 있습니다.</p>
      )}
    </>
  )
}
