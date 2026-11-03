// 근거 섹션 이름을 화면의 새 위치(1~4장·부록)로 바꾼다 (spec.md F4 "근거 섹션 이름 표시").
// 저장된 이름("2페이지 현금흐름 패턴 (코드 계산)")은 AI 입력 자료 이름이라 백엔드는 그대로 두고, 화면에서 근거 키를 보고 바꿔 붙인다.
// 그래서 기존 리포트도 새 이름으로 보인다. 목록에 없는 키(사업보고서·ECOS 등 원문 자료)는 저장된 이름 그대로.

/** 근거 키 → 새 위치 이름과 이동할 섹션 키. SWOT·외부 환경(source_index)과 과제(basis) 키를 함께 둔다. */
const PLACES: Record<string, { place: string; target: string }> = {
  // 7-B source_index 키
  'calc:core': { place: '1장', target: 'core_cards' },
  'calc:recent': { place: '2장', target: 'recent_results' },
  'calc:trend': { place: '부록 C', target: 'trend' },
  'calc:ratios': { place: '부록 C', target: 'ratios' },
  'calc:cashflow': { place: '부록 C', target: 'cashflow' },
  'calc:accounting': { place: '부록 C', target: 'accounting' },
  'calc:competitors': { place: '부록 E', target: 'competitors' },
  'p3:pest': { place: '부록 A', target: 'pest' },
  'p3:sensitivity': { place: '부록 A', target: 'macro' },
  'p3:five_forces': { place: '부록 B', target: 'five_forces' },
  'p3:topic1': { place: '2장', target: 'topics' },
  'p3:topic2': { place: '2장', target: 'topics' },
  'p3:topic3': { place: '2장', target: 'topics' },
  // 과제 근거(basis) 키
  swot_weaknesses: { place: '3장', target: 'swot' },
  swot_threats: { place: '3장', target: 'swot' },
  topic_1: { place: '2장', target: 'topics' },
  topic_2: { place: '2장', target: 'topics' },
  topic_3: { place: '2장', target: 'topics' },
  signals: { place: '1장', target: 'core_cards' },
  sensitivity: { place: '부록 A', target: 'macro' },
  cashflow: { place: '부록 C', target: 'cashflow' },
}

const OLD_PLACE = /^\s*\d\s*페이지\s*/

/** 화면에 보일 근거 이름과 이동할 섹션 (target이 없으면 리포트 안 섹션이 아니라 원문 자료) */
export function placeOf(key: string, savedLabel: string): { label: string; target: string | null } {
  const p = PLACES[key]
  if (!p) return { label: savedLabel, target: null }
  return { label: `${p.place} ${savedLabel.replace(OLD_PLACE, '')}`, target: p.target }
}
