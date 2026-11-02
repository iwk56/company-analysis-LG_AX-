// 연도별 표: 첫 칸은 항목 이름, 나머지는 연도별 숫자(오른쪽 정렬). 단위는 표 제목에 쓴다.
// noteKey가 있고 그 지표의 AI 주석이 있으면 항목 이름 옆에 ⓘ가 붙고, 누르면 아래 줄에 주석이 펼쳐진다.
import { useState } from 'react'
import type { ReactNode } from 'react'
import styles from '../app.module.css'
import type { Formatted } from '../format/number'
import { Num } from '../ui'
import { NoteButton, NotePanel } from './ai'

export interface TableRow {
  label: string
  cells: (Formatted | string)[]
  noteKey?: string
}

export default function YearTable({ title, unit, years, rows, footnote }: {
  title: string
  unit?: string
  years: number[]
  rows: TableRow[]
  footnote?: ReactNode
}) {
  const [openKey, setOpenKey] = useState<string | null>(null)
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
            <RowView key={r.label} row={r} years={years} open={r.noteKey !== undefined && openKey === r.noteKey}
              onToggle={() => setOpenKey(openKey === r.noteKey ? null : (r.noteKey ?? null))} />
          ))}
        </tbody>
      </table>
      {footnote && <p className={styles.footnote}>{footnote}</p>}
    </>
  )
}

function RowView({ row, years, open, onToggle }: { row: TableRow; years: number[]; open: boolean; onToggle: () => void }) {
  return (
    <>
      <tr>
        <td>{row.label}{row.noteKey && <> <NoteButton noteKey={row.noteKey} open={open} onToggle={onToggle} /></>}</td>
        {row.cells.map((c, i) => (
          <td key={years[i]}>{typeof c === 'string' ? c : <Num f={c} />}</td>
        ))}
      </tr>
      {open && row.noteKey && (
        <tr><td colSpan={years.length + 1} className={styles.notecell}><NotePanel noteKey={row.noteKey} /></td></tr>
      )}
    </>
  )
}
