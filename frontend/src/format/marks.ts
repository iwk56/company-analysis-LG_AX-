// 주가 차트에 공시 주제 날짜를 표시할 때, 날짜를 차트의 거래일로 옮긴다.

/** 표시 날짜(공시일 등)를 그 날짜 이후 첫 거래일로 옮긴다. 차트 기간 뒤(시세가 아직 없는 날)면 뺀다. 같은 거래일의 번호는 합친다. */
export function snapMarks(dates: string[], marks: { date: string; label: string }[]): { date: string; label: string }[] {
  const byDate = new Map<string, string[]>()
  for (const m of marks) {
    const d = dates.find((x) => x >= m.date)
    if (!d) continue
    const labels = byDate.get(d) ?? []
    if (!labels.includes(m.label)) labels.push(m.label)
    byDate.set(d, labels)
  }
  return [...byDate].map(([date, labels]) => ({ date, label: labels.join('') }))
}
