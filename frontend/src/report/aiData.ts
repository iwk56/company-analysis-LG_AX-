// 공시 확인·AI 결과(enrichments)를 읽는 훅과 근거 계산 (컴포넌트는 ai.tsx)
import { createContext, useContext } from 'react'
import type { Enrichment, Enrichments, ReportDetail } from '../api'

export interface AiState {
  report: ReportDetail
  e: Enrichments
  running: boolean
  error: string | null
  rerun: () => void
}

export const Ctx = createContext<AiState | null>(null)

export function useAi(): AiState {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error('AiProvider 안에서만 쓸 수 있습니다')
  return ctx
}

/** 성공한 작업의 내용. 없거나 실패·자료 없음이면 null */
export function useContent<K extends keyof Enrichments>(key: K): NonNullable<Enrichments[K]> extends Enrichment<infer T> ? T | null : never {
  const { e } = useAi()
  const row = e[key] as Enrichment | undefined
  return (row?.status === 'ok' ? row.content : null) as never
}

/** 작업 한 건의 상태 안내 (자료 없음·실패 사유). 성공했으면 null */
export function useNotice(key: keyof Enrichments): { status: 'empty' | 'failed'; message: string } | null {
  const { e } = useAi()
  const row = e[key] as Enrichment | undefined
  if (!row || row.status === 'ok') return null
  return { status: row.status, message: row.message ?? '자료 없음' }
}

export interface Evidence { label: string; url: string }

/** 주석 ③ 근거: 코드가 저장한 실제 출처 (AI가 쓰지 않는다) */
export function evidenceFor(r: ReportDetail, key: string): Evidence[] {
  const annual = r.sources.find((s) => s.kind === 'annual_report' && s.year === r.base_year)
  const interim = r.sources.find((s) => s.kind === 'interim_report')
  const out: Evidence[] = []
  if (key === 'net_vs_operating' && interim) out.push({ label: `${interim.label} · 연결재무제표 주석 (금융수익 및 금융비용)`, url: interim.url })
  else if (annual) out.push({ label: key === 'interest_coverage' ? `${annual.label} · 재무제표와 주석 (금융수익 및 금융비용)` : annual.label, url: annual.url })
  return out
}

export function useNote(key: string): { meaning: string | null; why: string | null; evidence: Evidence[] } | null {
  const { report } = useAi()
  const note = useContent('write_summaries')?.notes[key]
  if (!note) return null
  return { ...note, evidence: evidenceFor(report, key) }
}

