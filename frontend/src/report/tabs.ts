// 리포트 탭 (2026-11-04): 헤더는 위에 고정하고 아래를 탭으로 나눈다. 탭은 주소(?tab=)에 남아 공유·새로고침해도 같은 탭이 열린다.
import { createContext, useContext } from 'react'

export const TABS = [
  { key: 'summary', label: '한눈에' },
  { key: 'business', label: '사업 구조' },
  { key: 'industry', label: '산업·경쟁' },
  { key: 'earnings', label: '실적' },
  { key: 'position', label: '재무상태' },
  { key: 'cashflow', label: '현금흐름' },
  { key: 'value', label: '주주·가치평가' },
  { key: 'news', label: '최근 이슈' },
  { key: 'outlook', label: '전망·리스크' },
  { key: 'sources', label: '출처' },
] as const
// 2026-11-04 방향 전환(회사와 재무제표를 이해하려는 사람용): 재무제표 3개(손익·재무상태·현금흐름)를 탭으로 나눈다

export type TabKey = (typeof TABS)[number]['key']

export const isTab = (v: string | null): v is TabKey => TABS.some((t) => t.key === v)

/** 섹션 키 → 그 섹션이 있는 탭 (리포트 안 링크를 누르면 탭을 바꾼 뒤 그 섹션으로 이동한다) */
export const SECTION_TAB: Record<string, TabKey> = {
  core_cards: 'summary', glance: 'summary',
  overview: 'business', segments: 'business', business: 'business', subsidiaries: 'business',
  industry: 'industry', position: 'industry', five_forces: 'industry', pest: 'industry', macro: 'industry', competitors: 'industry', peer_insight: 'industry',
  recent_results: 'earnings', trend: 'earnings', income: 'earnings', mda: 'earnings', dupont: 'earnings',
  ratios: 'position', balance: 'position', profit_ratios: 'earnings',
  cashflow: 'cashflow', cash_analysis: 'cashflow',
  stocks: 'value',
  articles: 'news', topics: 'news',
  future: 'outlook', swot: 'outlook', caution: 'outlook', accounting: 'outlook',
  sources: 'sources',
}

export const TabCtx = createContext<(tab: TabKey) => void>(() => {})

export function useGoTab(): (tab: TabKey) => void {
  return useContext(TabCtx)
}
