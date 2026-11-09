// 근거 섹션 이름을 화면의 탭 이름으로 바꾼다 (2026-11-04: 1~4장·부록 구조 → 탭 구조).
// 저장된 이름("2페이지 현금흐름 패턴 (코드 계산)", "1장 업계 위치")은 AI 입력 자료 이름이라 백엔드는 그대로 두고,
// 화면에서 근거 키를 보고 앞의 옛 위치(N페이지·N장·부록 X)를 떼고 탭 이름을 붙인다. 그래서 기존 리포트도 새 이름으로 보인다.
// 목록에 없는 키(사업보고서·ECOS 등 원문 자료)는 저장된 이름 그대로.
import { SECTION_TAB, TABS } from '../report/tabs'

/** 근거 키 → 이동할 섹션 키. SWOT·외부 환경(source_index)과 과제(basis) 키를 함께 둔다. */
const TARGETS: Record<string, string> = {
  // 7-B source_index 키
  'calc:core': 'core_cards',
  'calc:recent': 'recent_results',
  'calc:trend': 'trend',
  'calc:ratios': 'ratios',
  'calc:cashflow': 'cashflow',
  'calc:accounting': 'accounting',
  'calc:competitors': 'competitors',
  'p3:pest': 'pest',
  'p3:sensitivity': 'macro',
  'p3:five_forces': 'five_forces',
  'p3:topic1': 'topics',
  'p3:topic2': 'topics',
  'p3:topic3': 'topics',
  // 8-D 보고서 서술·체크리스트
  'pdf:position': 'industry',
  'pdf:risks': 'caution',
  'pdf:mda': 'mda',
  'pdf:focus': 'future',
  mda: 'mda',
  risks: 'caution',
  // 과제 근거(basis) 키
  swot_weaknesses: 'swot',
  swot_threats: 'swot',
  topic_1: 'topics',
  topic_2: 'topics',
  topic_3: 'topics',
  signals: 'core_cards',
  sensitivity: 'macro',
  cashflow: 'cashflow',
}

const OLD_PLACE = /^\s*(\d\s*페이지|\d\s*장|부록\s*[A-Z])\s*/

function targetOf(key: string): string | null {
  if (TARGETS[key]) return TARGETS[key]
  if (key.startsWith('check:') || key.startsWith('check_')) return 'caution'
  return null
}

/** 화면에 보일 근거 이름과 이동할 섹션 (target이 없으면 리포트 안 섹션이 아니라 원문 자료) */
export function placeOf(key: string, savedLabel: string): { label: string; target: string | null } {
  const target = targetOf(key)
  if (!target) return { label: savedLabel, target: null }
  const tab = TABS.find((t) => t.key === SECTION_TAB[target])
  const name = savedLabel.replace(OLD_PLACE, '')
  return { label: tab ? `${tab.label} 탭 · ${name}` : name, target }
}
