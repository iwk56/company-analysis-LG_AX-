import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { useBlocker } from 'react-router-dom'
import { saveComment } from '../api'
import type { ApiError, ReportComment } from '../api'
import styles from '../app.module.css'
import type { SectionKey } from './sectionKeys'

export const MAX_COMMENT_LENGTH = 1000
export const UNSAVED_MESSAGE = '저장하지 않은 코멘트가 있습니다. 이동하면 쓰던 내용이 사라집니다. 이동할까요?'

interface CommentsState {
  reportId: number
  comments: Record<string, ReportComment>
  setComment: (key: string, comment: ReportComment | null) => void
  setDirty: (key: string, dirty: boolean) => void
}

const Ctx = createContext<CommentsState | null>(null)

/** 리포트 화면 전체를 감싼다. 코멘트 목록과 "저장하지 않은 코멘트" 상태를 들고, 페이지 이동·창 닫기를 막는다. */
export function CommentsProvider({ reportId, initial, children }: {
  reportId: number
  initial: Record<string, ReportComment>
  children: ReactNode
}) {
  const [comments, setComments] = useState(initial)
  const [dirtyKeys, setDirtyKeys] = useState<ReadonlySet<string>>(new Set())

  const setComment = useCallback((key: string, comment: ReportComment | null) => {
    setComments((prev) => {
      const next = { ...prev }
      if (comment) next[key] = comment
      else delete next[key]
      return next
    })
  }, [])
  const setDirty = useCallback((key: string, dirty: boolean) => {
    setDirtyKeys((prev) => {
      if (prev.has(key) === dirty) return prev
      const next = new Set(prev)
      if (dirty) next.add(key)
      else next.delete(key)
      return next
    })
  }, [])

  const hasUnsaved = dirtyKeys.size > 0

  // 앱 안의 이동(링크·뒤로 가기)
  const blocker = useBlocker(hasUnsaved)
  useEffect(() => {
    if (blocker.state !== 'blocked') return
    if (window.confirm(UNSAVED_MESSAGE)) blocker.proceed()
    else blocker.reset()
  }, [blocker])

  // 창 닫기·새로고침 (브라우저가 자체 확인 창을 띄운다)
  useEffect(() => {
    if (!hasUnsaved) return
    const onBeforeUnload = (e: BeforeUnloadEvent) => e.preventDefault()
    window.addEventListener('beforeunload', onBeforeUnload)
    return () => window.removeEventListener('beforeunload', onBeforeUnload)
  }, [hasUnsaved])

  const value = useMemo(() => ({ reportId, comments, setComment, setDirty }), [reportId, comments, setComment, setDirty])
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

/** 섹션 카드: 기존 카드 틀 + 맨 아래 내 코멘트란. 새 섹션도 이것으로 감싸면 같은 방식으로 코멘트가 붙는다. */
export function SectionCard({ sectionKey, children }: { sectionKey: SectionKey; children?: ReactNode }) {
  return (
    <section className={styles.card} data-section={sectionKey}>
      {children}
      <CommentBox sectionKey={sectionKey} />
    </section>
  )
}

function timeText(iso: string): string {
  return iso.slice(0, 16).replace('T', ' ')
}

function CommentBox({ sectionKey }: { sectionKey: SectionKey }) {
  const ctx = useContext(Ctx)
  const saved = ctx?.comments[sectionKey] ?? null
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const setDirty = ctx?.setDirty

  const showInput = editing || saved === null
  const dirty = showInput && draft !== (saved?.content ?? '')
  useEffect(() => {
    setDirty?.(sectionKey, dirty)
    return () => setDirty?.(sectionKey, false)
  }, [setDirty, sectionKey, dirty])

  if (!ctx) return null

  async function save() {
    if (!ctx) return
    setSaving(true)
    setError(null)
    try {
      const res = await saveComment(ctx.reportId, sectionKey, draft)
      ctx.setComment(sectionKey, res.comment)
      setEditing(false)
      setDraft('')
    } catch (e) {
      setError((e as ApiError).message) // 쓰던 내용은 그대로 둔다
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className={styles.comment}>
      <div className={styles.commenthead}>
        <b>내 코멘트</b>
        {saved && !showInput && <span className={styles.sub}>저장 {timeText(saved.updated_at)}</span>}
      </div>
      {!showInput && saved && (
        <>
          <p className={styles.commenttext}>{saved.content}</p>
          <button className={styles.link} onClick={() => { setDraft(saved.content); setEditing(true) }}>수정</button>
        </>
      )}
      {showInput && (
        <>
          <textarea
            className={styles.commentinput}
            value={draft}
            maxLength={MAX_COMMENT_LENGTH}
            rows={3}
            placeholder="이 섹션에 대한 내 메모를 적어 보세요"
            aria-label="내 코멘트"
            onChange={(e) => setDraft(e.target.value)}
          />
          <div className={styles.commentfoot}>
            <span className={styles.sub}>
              {draft.length}/{MAX_COMMENT_LENGTH}자{saved && ' · 비운 채 저장하면 코멘트가 삭제됩니다'}
              {dirty && <span className={styles.unsaved}> · 저장하지 않음</span>}
            </span>
            <span>
              {saved && <button className={styles.link} onClick={() => { setEditing(false); setError(null) }}>취소</button>}
              {' '}
              <button className={styles.primary} disabled={saving || !dirty} onClick={() => void save()}>
                {saving ? '저장 중…' : '저장'}
              </button>
            </span>
          </div>
        </>
      )}
      {error && <p className={styles.error}>{error}</p>}
    </div>
  )
}
