// 공시 확인·AI 결과 표시 조각: 상태 보관, "AI 작성/AI 추출" 표시, 한 줄 요약, 주석 ⓘ, 안내 배너
import { useCallback, useState } from 'react'
import type { ReactNode } from 'react'
import { runAi } from '../api'
import type { ApiError, Enrichment, Enrichments, ReportDetail } from '../api'
import styles from '../app.module.css'
import { Ctx, useAi, useContent, useNote } from './aiData'

export function AiProvider({ report, children }: { report: ReportDetail; children: ReactNode }) {
  const [e, setE] = useState<Enrichments>(report.enrichments ?? {})
  const [aiRetryable, setAiRetryable] = useState(report.ai_retryable)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const rerun = useCallback(() => {
    setRunning(true)
    setError(null)
    runAi(report.id)
      .then((res) => {
        setE(res.enrichments)
        setAiRetryable(res.ai_retryable)
      })
      .catch((err: ApiError) => setError(err.message))
      .finally(() => setRunning(false))
  }, [report.id])

  return <Ctx.Provider value={{ report, e, aiRetryable, running, error, rerun }}>{children}</Ctx.Provider>
}

/** "AI 작성/AI 추출" 표시. 그 결과가 가짜 응답(LLM_PROVIDER=fake)으로 만들어졌으면 "개발용 예시 응답"을 눈에 띄게 함께 붙인다. */
export function AiBadge({ task, kind = 'write' }: { task: keyof Enrichments; kind?: 'write' | 'extract' }) {
  const { e } = useAi()
  const fake = (e[task] as Enrichment | undefined)?.model === 'fake'
  return (
    <>
      <span className={styles.aibadge}>{kind === 'write' ? 'AI 작성' : 'AI 추출'}</span>
      {fake && <span className={styles.fakebadge} title="실제 AI가 만든 결과가 아닙니다">개발용 예시 응답</span>}
    </>
  )
}

const EXTERNAL_SUMMARY_KEYS = ['pest', 'five_forces', 'topics', 'macro'] as const

/** 섹션 맨 위 한 줄 요약 (회계 이슈는 write_accounting, 외부 환경 섹션은 write_external, 나머지는 write_summaries). */
export function Summary({ sectionKey }: { sectionKey: string }) {
  const main = useContent('write_summaries')?.summaries[sectionKey]
  const accounting = useContent('write_accounting')?.summary
  const external = useContent('write_external')?.summaries
  const ext = (EXTERNAL_SUMMARY_KEYS as readonly string[]).includes(sectionKey)
  const [task, text] = sectionKey === 'accounting' ? ['write_accounting', accounting] as const
    : ext ? ['write_external', external?.[sectionKey as (typeof EXTERNAL_SUMMARY_KEYS)[number]]] as const
    : ['write_summaries', main] as const
  if (!text) return null
  return <p className={styles.oneline}><AiBadge task={task} /> {text}</p>
}

export function AnalysisPoints({ text }: { text: string }) {
  const points = text.split(/(?<!\d)(?<=[.!?])\s+|\n+/u).map((point) => point.trim()).filter(Boolean)
  if (points.length === 0) return null
  return <ul className={styles.analysisPoints}>{points.map((point, index) => <li key={`${index}-${point}`}>{point}</li>)}</ul>
}

export function NoteButton({ noteKey, open, onToggle }: { noteKey: string; open: boolean; onToggle: () => void }) {
  const note = useNote(noteKey)
  if (!note) return null
  return (
    <button type="button" className={styles.infobtn} aria-expanded={open} aria-label="설명 보기" title="설명 보기" onClick={onToggle}>ⓘ</button>
  )
}

export function NotePanel({ noteKey }: { noteKey: string }) {
  const note = useNote(noteKey)
  if (!note) return null
  return (
    <div className={styles.infopanel}>
      {note.meaning && <p><b>의미</b> <AiBadge task={note.task} /> {note.meaning}</p>}
      {note.why && <p><b>왜 중요한가</b> <AiBadge task={note.task} /> {note.why}</p>}
      <p><b>근거</b> {note.evidence.length === 0 ? '출처 없음' : note.evidence.map((ev) => (
        <a key={ev.url + ev.label} href={ev.url} target="_blank" rel="noreferrer">{ev.label}</a>
      ))}</p>
    </div>
  )
}

/** 카드·제목 옆에 붙는 ⓘ와 펼침 패널 (제목 줄 안에서 쓰는 형태) */
export function InfoNote({ noteKey }: { noteKey: string }) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <NoteButton noteKey={noteKey} open={open} onToggle={() => setOpen((v) => !v)} />
      {open && <NotePanel noteKey={noteKey} />}
    </>
  )
}

/** 리포트 맨 위 안내: AI 해석이 없거나 일부 실패했을 때만 보인다. 누르면 없거나 실패한 작업만 다시 보낸다. */
export function AiBanner() {
  const { e, aiRetryable, running, error, rerun } = useAi()
  const rows = Object.values(e) as Enrichment[]
  const failed = aiRetryable.flatMap((key) => {
    const row = e[key as keyof Enrichments]
    return row?.status === 'failed' ? [row] : []
  })
  const messages = [...new Set(failed.map((x) => x.message ?? '실패'))]
  if (running) return <p className={styles.notice}>공시 확인·AI 해석을 만드는 중입니다… (최대 1~2분 걸릴 수 있습니다)</p>
  return (
    <>
      {error && <p className={styles.error}>{error}</p>}
      {rows.length === 0 && (
        <div className={styles.notice}>
          이 리포트에는 공시 확인·AI 해석이 아직 없습니다.{' '}
          <button className={styles.link} onClick={rerun}>AI 해석 만들기</button>
          <div className={styles.sub}>누르면 AI를 호출합니다. 한 번 만든 해석은 저장되어 다시 만들지 않습니다.</div>
        </div>
      )}
      {failed.length > 0 && (
        <div className={styles.notice}>
          공시 확인·AI 해석 {failed.length}건을 만들지 못했습니다: {messages.join(' / ')}{' '}
          <button className={styles.link} onClick={rerun}>실패한 것만 다시 시도</button>
        </div>
      )}
      {/* 2026-11-04 사용자 요청: 검사에서 버린 문장 수 안내는 화면에서 뺌 (개수는 run_enrich.py·show_costs로 확인) */}
    </>
  )
}
