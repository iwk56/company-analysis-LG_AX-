// 내 코멘트를 붙일 수 있는 섹션 키. 코멘트는 (리포트, 키)마다 하나씩 저장된다.
// 섹션을 추가할 때: ① 여기에 키를 더하고 ② 화면에서 <SectionCard sectionKey="새_키">로 감싼다.
// 백엔드는 키 모양(영소문자·숫자·밑줄)만 확인하므로 서버·DB는 바꾸지 않는다.
// 화면을 1~4장 + 부록으로 재구성(Phase 8-B)해도 기존 키는 그대로 쓴다 (spec.md F4 대응표).
export const SECTION_KEYS = [
  'core_cards', // 1장 핵심 지표 카드
  'overview', // 1장 기업 개요
  'segments', // 1장 사업부문 비중·BCG
  'recent_results', // 2장 최근 실적
  'topics', // 2장 공시 주제 묶음
  'swot', // 3장 SWOT
  'tasks', // 3장 회사의 과제와 필요한 역량 (8-B 새 키)
  'page4', // 4장 직무별 기여 아이디어
  'watch', // 4장 예상 면접 질문 (기존 지켜볼 점)
  'essay_numbers', // 4장 자기소개서에 쓸 숫자 모음 (8-B 새 키)
  'pest', // 부록 A PEST
  'macro', // 부록 A 경제 환경 민감도(환율·기준금리)
  'five_forces', // 부록 B 5 Forces
  'trend', // 부록 C 실적 추이
  'ratios', // 부록 C 재무비율
  'dupont', // 부록 C 듀퐁 분석
  'cashflow', // 부록 C 현금흐름 패턴
  'accounting', // 부록 C 회계 이슈 체크
  'stocks', // 부록 D 주가 흐름 비교
  'competitors', // 부록 E 경쟁사 비교
  // 'articles'(2장 네이버 검색결과)는 약관상 검색결과 뒤에 다른 내용을 붙이지 않으려고 코멘트란을 두지 않는다
  // 1장 종합 한 줄 평가·업계 위치는 코멘트란이 없다
] as const

export type SectionKey = (typeof SECTION_KEYS)[number]

/** 부록(기본 접힘) 섹션. [모두 펼치기]가 이 목록을 연다 */
export const APPENDIX_KEYS: readonly SectionKey[] = ['pest', 'macro', 'five_forces', 'trend', 'ratios', 'dupont', 'cashflow', 'accounting', 'stocks', 'competitors']
