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
  // 2026-11-03 취업 준비생 질문 구성으로 새로 만든 섹션 (코멘트는 화면에서 숨김)
  'industry', // 업계에서 어떤 위치예요? (점유율·경쟁사·고객)
  'future', // 앞으로 어디로 가요? (경영진단·연구개발·투자·신사업)
  'caution', // 조심할 건 없어요? (체크리스트·위험 요인)
  'mda', // 실적 탭: 경영진이 설명한 실적 (2026-11-04)
  'business', // 사업 구조 탭: 제품·매출 구성·부문 손익·생산·원재료·수주 (2026-11-04)
  'subsidiaries', // 사업 구조 탭: 출자 회사 (2026-11-04)
  'peer_insight', // 산업·경쟁 탭: 경쟁사와 비교한 해석 (2026-11-04)
  'income', // 실적 탭: 손익계산서 분석 (2026-11-04)
  'balance', // 재무상태 탭: 재무상태표 요약 (2026-11-04)
  'cash_analysis', // 현금흐름 탭: 현금흐름 분석 (2026-11-04)
  'profit_ratios', // 실적 탭: 수익성·성장성 비율 (2026-11-04)
  // 'articles'(2장 네이버 검색결과)는 약관상 검색결과 뒤에 다른 내용을 붙이지 않으려고 코멘트란을 두지 않는다
  // 1장 종합 한 줄 평가·업계 위치는 코멘트란이 없다
] as const

export type SectionKey = (typeof SECTION_KEYS)[number]

/** 부록(기본 접힘) 섹션. [모두 펼치기]가 이 목록을 연다 */
export const APPENDIX_KEYS: readonly SectionKey[] = ['pest', 'five_forces', 'trend', 'ratios', 'dupont', 'cashflow', 'accounting', 'stocks', 'competitors']
