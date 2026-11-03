// 백엔드 API (/api, 개발 중에는 Vite가 8000번 포트로 넘긴다)
import type { Metric } from './format/number'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(path, init)
  } catch {
    throw new ApiError(0, '서버에 연결할 수 없습니다. 백엔드가 켜져 있는지 확인해 주세요')
  }
  if (!res.ok) {
    let detail = `요청에 실패했습니다 (${res.status})`
    try {
      const body = await res.json()
      if (typeof body.detail === 'string') detail = body.detail
    } catch {
      /* 본문이 JSON이 아니면 기본 문구를 쓴다 */
    }
    throw new ApiError(res.status, detail)
  }
  return (await res.json()) as T
}

export interface SearchItem {
  corp_code: string
  corp_name: string
  stock_code: string
  industry_label: string
  is_financial: boolean
}
export interface SearchResult {
  query: string
  count: number
  message: string | null
  warning: string | null
  items: SearchItem[]
}

export interface JobStep {
  key: string
  label: string
  status: 'pending' | 'running' | 'done' | 'failed'
}
export interface Job {
  job_id: string
  corp_code: string
  corp_name: string
  status: 'running' | 'done' | 'failed'
  steps: JobStep[]
  report_id: number | null
  error: { step: string; step_label: string; message: string } | null
}

export interface ReportSummary {
  id: number
  corp_code: string
  corp_name: string
  created_at: string
  base_year: number
  competitor_count: number
}

export interface FinancialYear {
  year: number
  rcept_no: string | null
  missing_fields: string[]
  revenue: number | null
  operating_income: number | null
  net_income: number | null
  net_income_parent: number | null
  total_assets: number | null
  total_liabilities: number | null
  total_equity: number | null
  cfo: number | null
  cfi: number | null
  cff: number | null
  [field: string]: number | string | string[] | null
}

export type MetricMap = Record<string, Metric>
export interface Signal {
  level: string
  reason: string
}

export interface RecentResults {
  report_name: string
  year: number
  rcept_no: string
  basis: string
  period_current: string
  period_prior: string
  current: Record<string, number | null>
  prior: Record<string, number | null>
  notes: string[]
}

export interface CompetitorInfo {
  corp_code: string
  corp_name: string
  stock_code: string
  industry_name: string | null
  included: boolean
  excluded_reason: string | null
}

export interface ComparisonColumn {
  key: string
  label: string
  format: 'amount' | 'percent' | 'change' | 'multiple'
  higher_is_better: boolean | null
  ranked: boolean
  in_position?: boolean // 업계 내 위치 한 줄에 세는지 (5-B 이전 리포트에는 없음)
}
export interface ComparisonCell {
  value: number | null
  na_reason: string | null
  rank: number | null
  vs_average: 'above' | 'below' | 'same' | null
}
export interface Comparison {
  base_year: number
  columns: ComparisonColumn[]
  rows: {
    corp_code: string
    corp_name: string
    is_target: boolean
    basis: string
    source_url: string | null
    market_as_of?: string | null // 시가총액 기준일 (가장 최근 거래일)
    values: Record<string, ComparisonCell>
  }[]
  averages: Record<string, number | null>
  ranked_counts: Record<string, number>
  excluded: { corp_code: string; corp_name: string; reason: string }[]
  scatter: { corp_code: string; corp_name: string; is_target: boolean; x: number; y: number }[]
  position: { better: string[]; worse: string[]; same: string[]; unavailable: string[]; text: string }
  rank_rule: string
}

/** 네이버 검색결과 그대로 (검색어 강조 <b>와 HTML 문자가 들어 있음, format/naverText로 표시) */
export interface ArticleItem {
  title: string
  summary: string
  link: string
  published_at: string
}
/** null = 기사 수집 기능이 생기기 전에 만든 리포트, items가 비면 검색결과 없음 (expired면 보관 기간 21일이 지나 지움) */
export interface ArticleList {
  query: string
  collected_at: string
  period_start: string
  period_end: string
  expired: boolean
  expires_at: string
  items: ArticleItem[]
}
export interface MacroSeries {
  key: 'usd_krw' | 'base_rate' | string
  label: string
  unit: string
  stat_code: string
  source_url: string
  period_start: string
  period_end: string
  points: { date: string; value: number }[]
}

/** 기업별 최근 1년 일별 주가 (보통주). index는 기준일 종가 = 100 (백엔드가 계산) */
export interface StockSeries {
  corp_code: string
  corp_name: string
  stock_code: string
  is_target: boolean
  period_start: string
  period_end: string
  base_date: string | null
  points: { date: string; close: number; shares: number | null; market_cap: number | null; index: number }[]
  notes: string[]
}

export interface ReportComment {
  content: string
  updated_at: string
}

/** 공시 확인·AI 작업 결과 한 건. status: ok | empty(원문에 자료 없음·검증 못 함) | failed(다시 시도 가능) */
export interface Enrichment<T = unknown> {
  status: 'ok' | 'empty' | 'failed'
  by: 'code' | 'ai'
  model: string | null
  content: T | null
  message: string | null
  warnings: string[]
  created_at: string
}
export interface EmployeesContent {
  count: number
  avg_tenure_years: number | null
  avg_salary_won: number | null
  year: number
  url: string | null
}
export interface SegmentProduct { name: string; current_won: number; prior_won: number | null; share: number | null; growth: number | null }
export interface SegmentsContent { year: number; products: SegmentProduct[]; overseas_share: number | null }
export interface RndContent { amount_won: number; ratio_to_revenue: number | null }
export interface FinanceContent {
  interest_expense_won: number | null
  coverage_actual: number | null
  net_vs_operating: {
    period_label: string
    kind: 'interim' | 'annual'
    rcept_no: string | null
    net_income_parent: number
    operating_income: number
    items: { label: string; amount_won: number }[]
  } | null
}
export interface OverviewContent {
  overview: string | null
  bcg: { summary: string | null; segments: { name: string; comment: string }[] } | null
}
export interface SummariesContent {
  summaries: Record<string, string>
  notes: Record<string, { meaning: string | null; why: string | null }>
}
/** 회계 이슈 체크 판정: clear=이상 없음, check=확인 필요, unknown=확인 불가(원문과 대조하지 못함) */
export type Verdict = 'clear' | 'check' | 'unknown'
export interface AuditContent {
  verdict: 'clear' | 'check'
  opinion: string
  auditor: string | null
  fiscal_term: string
  settled_on: string | null
  emphasis: string[]
  key_audit_matters: string[]
  url: string | null
}
export interface CorrectionsContent {
  verdict: 'clear' | 'check'
  count: number
  items: { title: string; date: string; url: string }[]
  period_start: string
  period_end: string
}
export interface GoingConcernContent { verdict: 'clear' | 'check'; basis: 'emphasis' | 'ai'; quote: string }
export interface TextAmounts { state: 'none' | 'found' | 'unverified'; items: { party: string | null; amount_text: string }[] }
export interface RelatedPartyContent {
  verdict: Verdict
  threshold: number
  revenue_won: number | null
  sales_total_won: number | null
  sales_ratio: number | null
  purchases_total_won: number | null
  purchases_ratio: number | null
  top: { party: string; kind: string; amount_won: number }[]
  loans: TextAmounts
  guarantees: TextAmounts
}
export interface AccountingWriteContent {
  summary: string | null
  notes: Record<string, { meaning: string | null; why: string | null }>
}
// ───────── 7-B 외부 환경·SWOT·4페이지 (근거 키 → 이름·링크는 코드가 source_index에 붙인다)
export interface SourcedItem { text: string; sources: string[] }
export type SourceIndex = Record<string, { label: string; url: string | null }>
export interface DisclosureRef { rcept_no: string; title: string; date: string; url: string }
export interface DisclosuresContent {
  period_start: string
  period_end: string
  total: number
  items: (DisclosureRef & { filer: string })[]
}
export type Direction3 = '긍정' | '부정' | '혼재' | '자료 없음'
export interface ExternalContent {
  pest: Record<'politics' | 'economy' | 'society' | 'technology', SourcedItem[]>
  five_forces: { key: string; name: string; strength: '강' | '중' | '약'; reason: string; sources: string[] }[]
  topics: { title: string; summary: string; disclosures: DisclosureRef[] }[]
  sensitivity: {
    available: boolean
    export_share: number | null
    fx: { start_date: string; start: number; end_date: string; end: number; change: number } | null
    revenue?: { direction: Direction3; reason: string }
    cost?: { direction: Direction3; reason: string }
    sources?: string[]
  }
  watch: { checks: SourcedItem[]; questions: SourcedItem[] }
  summaries: Partial<Record<'pest' | 'five_forces' | 'topics' | 'macro' | 'watch', string>>
  disclosure_period: { period_start: string | null; period_end: string | null; total: number | null }
  source_index: SourceIndex
}
export interface SwotContent {
  verdict: string | null
  swot: Record<'strengths' | 'weaknesses' | 'opportunities' | 'threats', SourcedItem[]>
  source_index: SourceIndex
}
export type RoleKey = 'fpa' | 'accounting' | 'treasury' | 'research'
export interface Page4Content {
  summary: string | null
  tasks: { title: string; detail: string | null; basis: { key: string; label: string }[]; capability: string | null; ideas: Record<RoleKey, string | null> }[]
}
export interface Enrichments {
  audit_opinion?: Enrichment<AuditContent>
  corrections?: Enrichment<CorrectionsContent>
  extract_going_concern?: Enrichment<GoingConcernContent>
  extract_related_party?: Enrichment<RelatedPartyContent>
  write_accounting?: Enrichment<AccountingWriteContent>
  employees?: Enrichment<EmployeesContent>
  extract_segments?: Enrichment<SegmentsContent>
  extract_rnd?: Enrichment<RndContent>
  extract_finance?: Enrichment<FinanceContent>
  write_overview?: Enrichment<OverviewContent>
  write_summaries?: Enrichment<SummariesContent>
  disclosures?: Enrichment<DisclosuresContent>
  write_external?: Enrichment<ExternalContent>
  write_swot?: Enrichment<SwotContent>
  write_page4?: Enrichment<Page4Content>
}

export type PdfSlot = 'annual' | 'interim'
export type PdfKind = 'annual' | 'half' | 'q3' | 'q1'
export interface PdfGuideItem { kind: PdfKind; year: number; title: string; rcept_no: string; date: string; url: string }
export interface PdfGuide {
  company: { corp_code: string; corp_name: string }
  base_year: number | null // 기준 사업연도 N (최근 사업보고서)
  annual: PdfGuideItem | null
  interim: PdfGuideItem | null // N+1년의 최근 반기/3분기보고서
  message: string | null
}
export interface PdfCheck { key: string; label: string; ok: boolean | null; message: string } // ok null = 확인 안 함
export interface RevenueCheck { status: 'match' | 'mismatch' | 'not_found'; message: string; page: number | null }
export interface PdfUploadResult {
  upload_id: string | null // 거절이면 null (서버가 보관하지 않음)
  slot: PdfSlot
  file_name: string
  page_count: number
  accepted: boolean
  reasons: string[]
  checks: PdfCheck[]
  kind: PdfKind | null
  corrected: boolean
  period_start: string | null
  period_end: string | null
  revenue: RevenueCheck | null // ⑤ 매출액 대조 (경고만)
}
export interface PdfSection {
  key: string
  label: string
  found: boolean
  title: string | null
  page_start: number | null // PDF 뷰어 쪽 번호
  page_end: number | null
  chars: number
  over_limit: boolean // AI 입력 상한(12,000자)을 넘음
}
export interface ReportPdf {
  slot: PdfSlot
  file_name: string
  page_count: number
  kind: PdfKind
  corrected: boolean
  period_start: string
  period_end: string
  checks: PdfCheck[]
  revenue_check: RevenueCheck | null
  split_method: 'bookmarks' | 'headings'
  sections: PdfSection[]
}

export interface ReportDetail {
  id: number
  company: { corp_code: string; corp_name: string; stock_code: string; industry_name: string | null }
  created_at: string
  base_year: number
  data_as_of: string
  basis: string
  year_count: number
  interest_basis: string | null
  notes: string[]
  warnings: string[]
  competitors: CompetitorInfo[]
  financial_years: FinancialYear[]
  recent_results: RecentResults | null
  recent_reason: string | null
  results: {
    ratios: Record<string, MetricMap>
    dupont: Record<string, {
      metrics: MetricMap
      driver: { factor: string; changes: Record<string, number> } | null
      driver_na: string | null
    }>
    cashflow: Record<string, { pattern: string | null; na_reason: string | null }>
    signals: Record<string, Record<string, Signal | null>>
    recent_changes: {
      changes: MetricMap
      operating_margin_current: Metric
      operating_margin_prior: Metric
    } | null
    comparison?: Comparison
  }
  sources: { kind: string; year: number; label: string; rcept_no: string; url: string }[]
  articles: ArticleList | null
  macro: MacroSeries[] | null
  stocks?: StockSeries[] | null // null·없음 = 주가 수집 기능 이전에 만든 리포트
  enrichments: Enrichments
  ai_pending: string[] // 아직 만들지 않은 공시 확인·AI 작업 (기능이 나중에 생겨 기존 리포트에 없는 것 포함)
  comments: Record<string, ReportComment>
  pdfs?: ReportPdf[] // 빈 목록 = PDF 기능 이전에 만든 리포트
}

export const searchCompanies = (q: string) =>
  request<SearchResult>(`/api/companies/search?q=${encodeURIComponent(q)}`)

/** 확인된 사업보고서 PDF(필수)·반기/3분기 PDF(선택)로 리포트를 만든다. 경쟁사는 화면에서 보내지 않는다(구 경쟁사 선택 화면만 사용) */
export const createReport = (
  corpCode: string,
  uploads: { annual: string | null; interim?: string | null },
  competitors: string[] = [],
) =>
  request<Job>('/api/reports', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      corp_code: corpCode,
      annual_upload_id: uploads.annual,
      interim_upload_id: uploads.interim ?? null,
      competitors,
    }),
  })

export const getPdfGuide = (corpCode: string) =>
  request<PdfGuide>(`/api/pdf/guide?corp_code=${encodeURIComponent(corpCode)}`)

/** PDF를 올리면 서버가 바로 확인한다. otherUploadId: 다른 칸에 올린 PDF (같은 파일이면 거절) */
export function uploadPdf(corpCode: string, slot: PdfSlot, file: File, otherUploadId?: string | null) {
  const form = new FormData()
  form.append('corp_code', corpCode)
  form.append('slot', slot)
  if (otherUploadId) form.append('other_upload_id', otherUploadId)
  form.append('file', file)
  return request<PdfUploadResult>('/api/pdf/uploads', { method: 'POST', body: form })
}

export const getJob = (jobId: string) => request<Job>(`/api/reports/jobs/${jobId}`)

export const listReports = (q?: string) =>
  request<{ count: number; items: ReportSummary[] }>(`/api/reports${q ? `?q=${encodeURIComponent(q)}` : ''}`)

export const getReport = (id: number) => request<ReportDetail>(`/api/reports/${id}`)

export const deleteReport = (id: number) => request<{ deleted: number }>(`/api/reports/${id}`, { method: 'DELETE' })

export const saveComment = (reportId: number, sectionKey: string, content: string) =>
  request<{ section_key: string; comment: ReportComment | null }>(`/api/reports/${reportId}/comments/${sectionKey}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
  })

export const retryJob = (jobId: string) => request<Job>(`/api/reports/jobs/${jobId}/retry`, { method: 'POST' })

/** 공시 확인·AI 작업 중 아직 없거나 실패한 것만 실행한다 (이미 만든 해석은 다시 만들지 않는다) */
export const refreshArticles = (reportId: number) =>
  request<{ articles: ArticleList }>(`/api/reports/${reportId}/articles/refresh`, { method: 'POST' })
export const runAi = (reportId: number) => request<{ enrichments: Enrichments }>(`/api/reports/${reportId}/ai`, { method: 'POST' })
