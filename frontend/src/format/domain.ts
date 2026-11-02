/** 눈금이 깔끔하게 떨어지도록 1·2·5×10^n 단계로 맞춘다. */
function niceStep(rough: number): number {
  const base = 10 ** Math.floor(Math.log10(rough))
  const f = rough / base
  return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * base
}

/** 점과 이름표가 테두리에 붙지 않도록 데이터(와 평균선)를 모두 포함하는 축 범위를 정한다. 이름표는 점 위에 놓이므로 위쪽·오른쪽 여유를 더 둔다. */
export function paddedDomain(values: number[], pad: { low: number; high: number }): [number, number] {
  const lo = Math.min(...values)
  const hi = Math.max(...values)
  const span = Math.max(hi - lo, 2) // 점이 한 곳에 몰려도 축이 너무 좁아지지 않게 한다 (퍼센트 단위)
  const step = niceStep((span * (1 + pad.low + pad.high)) / 5)
  return [Math.floor((lo - span * pad.low) / step) * step, Math.ceil((hi + span * pad.high) / step) * step]
}
