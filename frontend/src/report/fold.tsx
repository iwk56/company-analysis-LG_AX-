// 부록 접힘과 리포트 안 이동 (spec.md F4 "부록 접힘 동작")
// - 부록 섹션은 기본 접힘. 접혀도 제목과 한 줄 요약은 보이고, 내용은 지우지 않고 숨기기만 한다(쓰던 코멘트 유지).
// - 펼침 상태는 저장하지 않는다(리포트를 다시 열면 모두 접힘).
// - 근거 링크는 jump(섹션 키)로 해당 섹션을 펼치고 그 위치로 이동한다.
import { useCallback, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import styles from '../app.module.css'
import { NavCtx, useNav } from './foldData'
import { APPENDIX_KEYS } from './sectionKeys'

export function NavProvider({ children, onJump }: { children: ReactNode; onJump?: (key: string) => void }) {
  const [open, setOpen] = useState<ReadonlySet<string>>(new Set())
  const toggle = useCallback((key: string) => {
    setOpen((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }, [])
  const setAll = useCallback((v: boolean) => setOpen(v ? new Set(APPENDIX_KEYS) : new Set()), [])
  const jump = useCallback((key: string) => {
    setOpen((prev) => (prev.has(key) ? prev : new Set(prev).add(key)))
    onJump?.(key) // 다른 탭에 있는 섹션이면 탭을 먼저 바꾼다 (2026-11-04)
    // 탭이 바뀌어 그려진 뒤 이동해야 그 섹션을 찾을 수 있다
    setTimeout(() => document.querySelector(`[data-section="${key}"]`)?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 60)
  }, [onJump])
  const value = useMemo(() => ({ isOpen: (k: string) => open.has(k), toggle, setAll, jump }), [open, toggle, setAll, jump])
  return <NavCtx.Provider value={value}>{children}</NavCtx.Provider>
}

/** 부록 전체 (2026-11-04 사용자 요청: 접기·펼치기 없앰 → 모든 섹션을 펼친 채로 보여 준다) */
export function Appendix({ children }: { children: ReactNode }) {
  return <>{children}</>
}

/** 부록 묶음 제목 (A. 거시 …) */
export function AppendixGroup({ title }: { title: string }) {
  return <h2 className={styles.appgroup}>{title}</h2>
}

/** 리포트 안 섹션으로 이동하는 링크 (부록이면 펼친 뒤 이동) */
export function JumpLink({ to, children }: { to: string; children: ReactNode }) {
  const nav = useNav()
  return (
    <a href={`#${to}`} onClick={(e) => { e.preventDefault(); nav?.jump(to) }}>{children}</a>
  )
}

/** 본문 안의 심화 섹션 묶음. 2026-11-04부터 접지 않고 그대로 보여 준다 (예전에는 기본 접힘) */
export function Folds({ children }: { children: ReactNode }) {
  return <>{children}</>
}
