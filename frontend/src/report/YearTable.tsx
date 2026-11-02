// 연도별 표: 첫 칸은 항목 이름, 나머지는 연도별 숫자(오른쪽 정렬). 단위는 표 제목에 쓴다.
import type { ReactNode } from 'react'
import styles from '../app.module.css'
import type { Formatted } from '../format/number'
import { Num } from '../ui'

export interface TableRow {
  label: string
  cells: (Formatted | string)[]
}

export default function YearTable({ title, unit, years, rows, footnote }: {
  title: string
  unit?: string
  years: number[]
  rows: TableRow[]
  footnote?: ReactNode
}) {
  return (
    <>
      <p className={styles.tabletitle}>
        {title}
        {unit && <span className={styles.unit}>(단위: {unit})</span>}
      </p>
      <table className={styles.table}>
        <thead>
          <tr>
            <th>항목</th>
            {years.map((y) => <th key={y}>{y}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.label}>
              <td>{r.label}</td>
              {r.cells.map((c, i) => (
                <td key={years[i]}>{typeof c === 'string' ? c : <Num f={c} />}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {footnote && <p className={styles.footnote}>{footnote}</p>}
    </>
  )
}
