// 내 코멘트를 붙일 수 있는 섹션 키. 코멘트는 (리포트, 키)마다 하나씩 저장된다.
// 섹션을 추가할 때(예: 3·4페이지): ① 여기에 키를 더하고 ② 화면에서 <SectionCard sectionKey="새_키">로 감싼다.
// 백엔드는 키 모양(영소문자·숫자·밑줄)만 확인하므로 서버·DB는 바꾸지 않는다.
export const SECTION_KEYS = [
  'overview', // 1페이지 기업 개요
  'segments', // 1페이지 사업부문 비중
  'swot', // 1페이지 종합 평가·SWOT
  'core_cards', // 1페이지 핵심 지표 카드
  'recent_results', // 2페이지 최근 실적
  'trend', // 실적 추이
  'ratios', // 재무비율
  'dupont', // 듀퐁 분석
  'cashflow', // 현금흐름 패턴
  'accounting', // 회계 이슈 체크
  'competitors', // 경쟁사 비교
  'stocks', // 주가 흐름 비교
  'pest', // 3페이지 PEST
  'five_forces', // 3페이지 5 Forces
  'topics', // 3페이지 공시 주제 묶음
  'macro', // 3페이지 경제 환경 민감도(환율·기준금리)
  'watch', // 3페이지 지켜볼 점
  'page4', // 4페이지 회사의 과제와 나의 기여
  // 'articles'(3페이지 네이버 검색결과)는 약관상 검색결과 뒤에 다른 내용을 붙이지 않으려고 코멘트란을 두지 않는다
] as const

export type SectionKey = (typeof SECTION_KEYS)[number]
