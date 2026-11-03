// 부록 접힘과 리포트 안 이동 (spec.md F4 "부록 접힘 동작")
// - 부록 섹션은 기본 접힘. 접혀도 제목과 한 줄 요약은 보이고, 내용은 지우지 않고 숨기기만 한다(쓰던 코멘트 유지).
// - 펼침 상태는 저장하지 않는다(리포트를 다시 열면 모두 접힘).
// - 1~4장의 근거 링크는 jump(섹션 키)로 해당 섹션을 펼치고 그 위치로 이동한다.
import { useCallback, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import styles from '../app.module.css'
import { AppendixScope, NavCtx, useNav } from './foldData'
import { APPENDIX_KEYS } from './sectionKeys'

export function NavProvider({ children }: { children: ReactNode }) {
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
    // 펼친 뒤(다음 화면 그리기) 이동해야 페이지 끝 근처 섹션도 맨 위까지 올라온다
    requestAnimationFrame(() => document.querySelector(`[data-section="${key}"]`)?.scrollIntoView({ behavior: 'smooth', block: 'start' }))
  }, [])
  const value = useMemo(() => ({ isOpen: (k: string) => open.has(k), toggle, setAll, jump }), [open, toggle, setAll, jump])
  return <NavCtx.Provider value={value}>{children}</NavCtx.Provider>
}

/** 부록 전체: 맨 위 [모두 펼치기]/[모두 접기], 안의 SectionCard는 접을 수 있게 된다 */
export function Appendix({ children }: { children: ReactNode }) {
  const nav = useNav()
  return (
    <AppendixScope.Provider value={true}>
      <div className={styles.appendixbar}>
        <span className={styles.sub}>부록은 근거가 되는 심화 분석입니다. 섹션 제목을 누르면 펼칩니다.</span>
        <span>
          <button type="button" className={styles.link} onClick={() => nav?.setAll(true)}>모두 펼치기</button>
          {' · '}
          <button type="button" className={styles.link} onClick={() => nav?.setAll(false)}>모두 접기</button>
        </span>
      </div>
      {children}
    </AppendixScope.Provider>
  )
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
