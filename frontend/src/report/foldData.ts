// 부록 접힘·리포트 안 이동 상태를 읽는 훅 (컴포넌트는 fold.tsx)
import { createContext, useContext } from 'react'

export interface NavState {
  isOpen: (key: string) => boolean
  toggle: (key: string) => void
  setAll: (open: boolean) => void
  jump: (key: string) => void
}

export const NavCtx = createContext<NavState | null>(null)
export const AppendixScope = createContext(false)

export function useNav(): NavState | null {
  return useContext(NavCtx)
}

/** 이 섹션이 부록 안에 있으면 접힘 상태와 토글. 1~4장이면 null */
export function useFold(key: string): { open: boolean; toggle: () => void } | null {
  const nav = useContext(NavCtx)
  const inAppendix = useContext(AppendixScope)
  if (!nav || !inAppendix) return null
  return { open: nav.isOpen(key), toggle: () => nav.toggle(key) }
}
