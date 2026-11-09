// 차트 색 (분석 기업·강조는 COLORS[1])
export const COLORS = ['#2456a6', '#d97706', '#1b873f', '#8e44ad']

// 핵심 지표 카드의 축별 강조 색 (왼쪽 테두리). 신호등 색(양호 초록·주의 황토·위험 빨강, index.css)과
// 겹치지 않도록 파랑 계열로만 고름 — 카드가 8개로 늘어도 같은 축이면 같은 색을 쓴다.
export const AXIS_COLORS: Record<'growth' | 'profit' | 'stability' | 'cash', string> = {
  growth: '#2456a6', // 성장성 — 회사가 커지는 중인지
  profit: '#7c3aed', // 수익성 — 돈을 남기는지
  stability: '#0f766e', // 안정성 — 빚 부담이 괜찮은지
  cash: '#475569', // 현금의 질 — 숫자가 진짜인지 검증
}
