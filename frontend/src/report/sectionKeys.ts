// 내 코멘트를 붙일 수 있는 섹션 키. 코멘트는 (리포트, 키)마다 하나씩 저장된다.
// 섹션을 추가할 때(예: 3·4페이지): ① 여기에 키를 더하고 ② 화면에서 <SectionCard sectionKey="새_키">로 감싼다.
// 백엔드는 키 모양(영소문자·숫자·밑줄)만 확인하므로 서버·DB는 바꾸지 않는다.
export const SECTION_KEYS = [
  'core_cards', // 1페이지 핵심 지표 카드
  'recent_results', // 2페이지 최근 실적
  'trend', // 실적 추이
  'ratios', // 재무비율
  'dupont', // 듀퐁 분석
  'cashflow', // 현금흐름 패턴
  'competitors', // 경쟁사 비교
  'macro', // 3페이지 환율·기준금리
  'articles', // 3페이지 최근 기사
] as const

export type SectionKey = (typeof SECTION_KEYS)[number]
