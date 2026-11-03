import { describe, expect, it } from 'vitest'
import { snapMarks } from './marks'

describe('snapMarks', () => {
  const dates = ['2026-10-23', '2026-10-26', '2026-10-27', '2026-10-28', '2026-10-30']
  it('거래일이면 그대로, 휴일이면 다음 거래일로 옮긴다', () => {
    expect(snapMarks(dates, [{ date: '2026-10-26', label: '①' }, { date: '2026-10-25', label: '③' }])).toEqual([
      { date: '2026-10-26', label: '①③' },
    ])
  })
  it('차트 마지막 날 뒤의 날짜는 뺀다', () => {
    expect(snapMarks(dates, [{ date: '2026-11-02', label: '②' }])).toEqual([])
  })
  it('같은 날 같은 번호는 한 번만', () => {
    expect(snapMarks(dates, [{ date: '2026-10-28', label: '①' }, { date: '2026-10-28', label: '①' }, { date: '2026-10-28', label: '②' }])).toEqual([
      { date: '2026-10-28', label: '①②' },
    ])
  })
})
