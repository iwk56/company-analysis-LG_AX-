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
export function evidenceFor(r: ReportDetail, key: string, e?: Enrichments): Evidence[] {
  const annual = r.sources.find((s) => s.kind === 'annual_report' && s.year === r.base_year)
  const interim = r.sources.find((s) => s.kind === 'interim_report')
  const out: Evidence[] = []
  if (key === 'net_vs_operating' && interim) out.push({ label: `${interim.label} · 연결재무제표 주석 (금융수익 및 금융비용)`, url: interim.url })
  else if (key === 'audit_opinion' || key === 'going_concern') {
    const url = e?.audit_opinion?.content?.url ?? annual?.url
    if (url) out.push({ label: `${r.base_year} 사업보고서 · 회계감사인의 감사의견 등`, url })
  } else if (key === 'corrections') {
    for (const it of e?.corrections?.content?.items.slice(0, 3) ?? []) out.push({ label: `${it.title} (${it.date})`, url: it.url })
    if (out.length === 0 && annual) out.push({ label: `${annual.label} (정정 여부는 DART 공시 목록에서 확인)`, url: annual.url })
  } else if (key === 'related_party' && annual) out.push({ label: `${annual.label} · 재무제표 주석 (특수관계자)`, url: annual.url })
  else if (annual) out.push({ label: key === 'interest_coverage' ? `${annual.label} · 재무제표와 주석 (금융수익 및 금융비용)` : annual.label, url: annual.url })
  return out
}

/** 주석 ⓘ 내용. 재무 주석은 write_summaries, 회계 이슈 4개는 write_accounting에 있다. */
export function useNote(key: string): { meaning: string | null; why: string | null; evidence: Evidence[]; task: 'write_summaries' | 'write_accounting' } | null {
  const { report, e } = useAi()
  const main = useContent('write_summaries')?.notes[key]
  const accounting = useContent('write_accounting')?.notes[key]
  const note = main ?? accounting
  if (!note) return null
  return { ...note, evidence: evidenceFor(report, key, e), task: main ? 'write_summaries' : 'write_accounting' }
}
