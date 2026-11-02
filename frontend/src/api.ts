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
  format: 'amount' | 'percent' | 'change'
  higher_is_better: boolean | null
  ranked: boolean
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
    values: Record<string, ComparisonCell>
  }[]
  averages: Record<string, number | null>
  ranked_counts: Record<string, number>
  excluded: { corp_code: string; corp_name: string; reason: string }[]
  scatter: { corp_code: string; corp_name: string; is_target: boolean; x: number; y: number }[]
  position: { better: string[]; worse: string[]; same: string[]; unavailable: string[]; text: string }
  rank_rule: string
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
}

export const searchCompanies = (q: string) =>
  request<SearchResult>(`/api/companies/search?q=${encodeURIComponent(q)}`)

export const createReport = (corpCode: string, competitors: string[]) =>
  request<Job>('/api/reports', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ corp_code: corpCode, competitors }),
  })

export const getJob = (jobId: string) => request<Job>(`/api/reports/jobs/${jobId}`)

export const listReports = (q?: string) =>
  request<{ count: number; items: ReportSummary[] }>(`/api/reports${q ? `?q=${encodeURIComponent(q)}` : ''}`)

export const getReport = (id: number) => request<ReportDetail>(`/api/reports/${id}`)

export const deleteReport = (id: number) => request<{ deleted: number }>(`/api/reports/${id}`, { method: 'DELETE' })
