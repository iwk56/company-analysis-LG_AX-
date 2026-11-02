// 공통 표시 조각: 숫자(음수 빨강·회색 처리)와 신호등
import styles from './app.module.css'
import type { Formatted } from './format/number'
import { signalView } from './format/number'

export function Num({ f }: { f: Formatted }) {
  const cls = f.negative ? styles.neg : f.muted ? styles.na : undefined
  return <span className={cls}>{f.text}</span>
}

export function SignalBadge({ level, reason }: { level: string | null | undefined; reason?: string }) {
  const v = signalView(level)
  if (!v) return <span className={styles.na}>판정 없음(첫 연도)</span>
  return (
    <span className={`${styles.signal} ${styles[v.tone]}`} title={reason}>
      <span className={styles.dot} aria-hidden="true" />
      {v.label}
    </span>
  )
}
