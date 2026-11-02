// 카드의 "전년 대비" 표시용. 백엔드가 이미 계산한 두 값의 차이만 구한다(새 지표를 만들지 않는다).

export type Direction = 'up' | 'down' | 'flat'

export const ARROW: Record<Direction, string> = { up: '▲', down: '▼', flat: '―' }

/** 비율끼리의 차이 (0.55 − 0.64 = −0.09 → −9.0%p로 표시할 값) */
export function difference(current: number | null | undefined, prior: number | null | undefined): number | null {
  if (typeof current !== 'number' || typeof prior !== 'number') return null
  return current - prior
}

/** 금액의 전년 대비 증감률: (당기 − 전기) ÷ |전기|. 전기가 0이거나 없으면 null */
export function relativeChange(current: number | null | undefined, prior: number | null | undefined): number | null {
  if (typeof current !== 'number' || typeof prior !== 'number' || prior === 0) return null
  return (current - prior) / Math.abs(prior)
}

/** 반올림했을 때 소수 첫째 자리까지 같으면 변화 없음(―)으로 본다 */
export function direction(x: number | null): Direction | null {
  if (x === null) return null
  const tenths = Math.round(Math.abs(x) * 1000 + 1e-9) // 비율 0.0005 단위 = 표시상 0.05%
  if (tenths < 1) return 'flat'
  return x > 0 ? 'up' : 'down'
}
