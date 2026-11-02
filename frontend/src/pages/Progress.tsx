import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ApiError, getJob } from '../api'
import type { Job } from '../api'
import styles from '../app.module.css'

const POLL_MS = 1000
const MARK = { pending: '대기', running: '진행 중…', done: '완료', failed: '실패' } as const

export default function Progress() {
  const { jobId = '' } = useParams()
  const navigate = useNavigate()
  const [job, setJob] = useState<Job | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let stopped = false
    let timer: number | undefined
    async function poll() {
      try {
        const j = await getJob(jobId)
        if (stopped) return
        setJob(j)
        if (j.status === 'done' && j.report_id !== null) {
          navigate(`/reports/${j.report_id}`, { replace: true })
          return
        }
        if (j.status === 'running') timer = window.setTimeout(poll, POLL_MS)
      } catch (e) {
        if (stopped) return
        const err = e as ApiError
        setError(err.status === 404 ? `${err.message}. 홈에서 다시 만들어 주세요.` : err.message)
      }
    }
    void poll()
    return () => {
      stopped = true
      window.clearTimeout(timer)
    }
  }, [jobId, navigate])

  return (
    <section className={styles.card}>
      <h3>{job ? `${job.corp_name} 리포트 생성` : '리포트 생성'}</h3>
      {error && <p className={styles.error}>{error}</p>}
      {job && (
        <ol className={styles.steps}>
          {job.steps.map((s) => (
            <li key={s.key} className={s.status === 'done' ? styles.stepdone : s.status === 'running' ? styles.steprunning : s.status === 'failed' ? styles.stepfailed : styles.muted}>
              {s.label} — {MARK[s.status]}
            </li>
          ))}
        </ol>
      )}
      {job?.status === 'failed' && job.error && (
        <p className={styles.error}>
          “{job.error.step_label}” 단계에서 실패했습니다: {job.error.message}
        </p>
      )}
      {(error || job?.status === 'failed') && <Link to="/">홈으로</Link>}
    </section>
  )
}
