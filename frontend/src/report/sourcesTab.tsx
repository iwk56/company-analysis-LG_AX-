// "출처" 탭 (2026-11-04): 리포트에 쓴 자료를 종류별로 모은다. 링크는 저장된 실제 주소만 쓰고 새로 지어내지 않는다.
import type { ReactNode } from 'react'
import type { Enrichment, ReportDetail } from '../api'
import styles from '../app.module.css'
import { useAi } from './aiData'

const DART_VIEWER = 'https://dart.fss.or.kr/dsaf001/main.do?rcpNo='

function Group({ title, note, children }: { title: string; note?: ReactNode; children: ReactNode }) {
  return (
    <div className={styles.part}>
      <div className={styles.parttitle}>{title}</div>
      {children}
      {note && <p className={styles.footnote}>{note}</p>}
    </div>
  )
}

/** 원문 기록의 확인 메시지에 남긴 접수번호 → 공시뷰어 링크 */
function rceptOf(checks: { message?: string }[] | undefined): string | null {
  for (const c of checks ?? []) {
    const m = c.message?.match(/접수번호 (\d{14})/)
    if (m) return m[1]
  }
  return null
}

export function SourcesTab({ r }: { r: ReportDetail }) {
  const { e } = useAi()
  const audit = e.audit_opinion?.content
  const disc = e.disclosures?.content
  const models = [...new Set(Object.values(e).map((x) => (x as Enrichment | undefined)?.model).filter((m): m is string => !!m))]
  const a = r.articles

  return (
    <section className={styles.card} data-section="sources">
      <h3>출처</h3>
      <p className={styles.sub}>이 리포트에 쓴 자료입니다. 숫자는 코드가 아래 자료로 계산했고, AI는 아래 자료 안에서만 해석했습니다.</p>

      <Group title="재무제표 (DART 공시)" note="OpenDART 재무제표 API로 받은 값입니다. 5년 추이와 비율은 코드가 계산했습니다.">
        <ul className={styles.sources}>
          {r.sources.map((s) => (
            <li key={s.rcept_no + s.label}><a href={s.url} target="_blank" rel="noreferrer">{s.label}</a> <span className={styles.sub}>접수번호 {s.rcept_no}</span></li>
          ))}
        </ul>
      </Group>

      {(r.pdfs ?? []).length > 0 && (
        <Group title="보고서 본문 (회사 설명·경영진단·연구개발·위험 등)" note="AI가 이 본문에서 내용을 뽑았고, 인용은 코드가 원문과 글자 그대로 대조해 맞는 것만 남겼습니다.">
          <ul className={styles.sources}>
            {(r.pdfs ?? []).map((p) => {
              const rcept = rceptOf(p.checks)
              const used = p.sections.filter((s) => s.found).map((s) => s.label)
              return (
                <li key={p.slot}>
                  {rcept ? <a href={DART_VIEWER + rcept} target="_blank" rel="noreferrer">{p.file_name}</a> : p.file_name}
                  <div className={styles.footnote}>사용한 부분: {used.join(', ') || '없음'}</div>
                </li>
              )
            })}
          </ul>
        </Group>
      )}

      <Group title="기타 DART 공시">
        <ul className={styles.sources}>
          {audit?.url && <li><a href={audit.url} target="_blank" rel="noreferrer">감사보고서 (감사의견 {audit.opinion})</a> <span className={styles.sub}>{audit.auditor ?? ''}</span></li>}
          {disc && <li>최근 공시 목록 {disc.total}건 <span className={styles.sub}>({disc.period_start} ~ {disc.period_end}, 공시 주제 묶음에 사용)</span></li>}
        </ul>
      </Group>

      <Group title="경제 지표">
        {(r.macro ?? []).length === 0 ? <p className={styles.muted}>없음</p> : (
          <ul className={styles.sources}>
            {(r.macro ?? []).map((m) => (
              <li key={m.key}><a href={m.source_url} target="_blank" rel="noreferrer">한국은행 ECOS · {m.label}</a> <span className={styles.sub}>통계표 {m.stat_code} · {m.period_start} ~ {m.period_end}</span></li>
            ))}
          </ul>
        )}
      </Group>

      <Group title="주가">
        {(r.stocks ?? []).length === 0 ? <p className={styles.muted}>없음</p> : (
          <ul className={styles.sources}>
            {(r.stocks ?? []).map((s) => (
              <li key={s.corp_code}>공공데이터포털 금융위원회 주식시세정보 · {s.corp_name} <span className={styles.sub}>{s.period_start} ~ {s.period_end}</span></li>
            ))}
          </ul>
        )}
      </Group>

      <Group title="뉴스" note="네이버 검색결과는 약관에 따라 받은 그대로 보여 주며 AI 해석에는 쓰지 않습니다.">
        {a === null ? <p className={styles.muted}>없음</p> : (
          <p>네이버 뉴스 검색 API · 수집 {a.collected_at.slice(0, 10)}{a.groups && a.groups.length > 1 ? ` · 검색어 ${a.groups.map((g) => `“${g.query}”`).join(', ')}` : ` · 검색어 “${a.query}”`}</p>
        )}
      </Group>

      {[...r.warnings, ...r.notes].length > 0 && (
        <Group title="자료 참고 사항">
          <ul className={styles.sources}>
            {[...r.warnings, ...r.notes].map((m) => <li key={m}>{m}</li>)}
          </ul>
        </Group>
      )}

      <Group title="분류·AI">
        <ul className={styles.sources}>
          <li>업종: 통계청 한국표준산업분류(KSIC) 10차 · {r.company.industry_name ?? '자료 없음'}</li>
          <li>AI 모델: {models.length ? models.map((m) => (m === 'fake' ? '개발용 예시 응답' : m)).join(', ') : '사용 안 함'} <span className={styles.sub}>(OpenAI)</span></li>
        </ul>
      </Group>
    </section>
  )
}
