// 2페이지 회계 이슈 체크리스트: 감사의견·계속기업 불확실성·정정공시·특수관계자 거래 (이상 없음 / 확인 필요 / 확인 불가)
import { useState } from 'react'
import type { ReactNode } from 'react'
import type { Enrichment, ReportDetail, TextAmounts, Verdict } from '../api'
import styles from '../app.module.css'
import { formatPercent, formatWonCard } from '../format/number'
import { AiBadge, NoteButton, NotePanel, Summary } from './ai'
import { useAi, useContent } from './aiData'
import { SectionCard } from './comments'

const VERDICT_LABEL: Record<Verdict, { text: string; tone: string }> = {
  clear: { text: '이상 없음', tone: 'good' },
  check: { text: '확인 필요', tone: 'warn' },
  unknown: { text: '확인 불가(원문과 대조하지 못함)', tone: 'unknown' },
}

function VerdictBadge({ verdict }: { verdict: Verdict }) {
  const v = VERDICT_LABEL[verdict]
  return (
    <span className={`${styles.signal} ${styles[v.tone]}`}>
      <span className={styles.dot} aria-hidden="true" />
      {v.text}
    </span>
  )
}

/** 저장된 작업 한 건의 판정. 성공하지 못했으면(자료 없음·실패·아직 안 만듦) 확인 불가 */
const verdictOf = (row: Enrichment<{ verdict: Verdict }> | undefined): Verdict => (row?.status === 'ok' && row.content ? row.content.verdict : 'unknown')

function Item({ name, noteKey, verdict, children }: { name: string; noteKey: string; verdict: Verdict; children: ReactNode }) {
  const [open, setOpen] = useState(false)
  return (
    <div className={styles.checkitem}>
      <div className={styles.checkhead}>
        <span className={styles.itemname}>{name}</span>
        <VerdictBadge verdict={verdict} />
        <NoteButton noteKey={noteKey} open={open} onToggle={() => setOpen((v) => !v)} />
      </div>
      {open && <NotePanel noteKey={noteKey} />}
      <div className={styles.checkbody}>{children}</div>
    </div>
  )
}

/** 성공하지 못한 작업의 사유 (자료 없음·실패·아직 안 만듦) */
function Why({ row }: { row: Enrichment | undefined }) {
  if (row?.status === 'ok') return null
  return <p className={styles.muted}>{row ? row.message ?? '자료 없음' : '아직 확인하지 않았습니다'}</p>
}

function Link({ url, children = '원문' }: { url: string | null | undefined; children?: ReactNode }) {
  return url ? <a href={url} target="_blank" rel="noreferrer">{children}</a> : null
}

function Audit() {
  const { e } = useAi()
  const row = e.audit_opinion
  const c = useContent('audit_opinion')
  return (
    <Item name="감사의견" noteKey="audit_opinion" verdict={verdictOf(row)}>
      <Why row={row} />
      {c && (
        <>
          <p>
            <b>{c.opinion}</b> · 감사인 {c.auditor ?? '자료 없음'} · {c.fiscal_term}(당기{c.settled_on ? `, 결산일 ${c.settled_on}` : ''}) · OpenDART 감사의견 자료 <Link url={c.url} />
          </p>
          {c.emphasis.length > 0 ? <p>강조사항: {c.emphasis.join(' / ')}</p> : <p className={styles.muted}>강조사항 없음</p>}
          {c.key_audit_matters.length > 0 && (
            <>
              <p className={styles.muted}>핵심감사사항 (감사인이 특히 신경 쓴 부분)</p>
              <ul>{c.key_audit_matters.map((m) => <li key={m}>{m}</li>)}</ul>
            </>
          )}
        </>
      )}
    </Item>
  )
}

function GoingConcern({ r }: { r: ReportDetail }) {
  const { e } = useAi()
  const row = e.extract_going_concern
  const c = useContent('extract_going_concern')
  const link = e.audit_opinion?.content?.url ?? r.sources.find((s) => s.kind === 'annual_report' && s.year === r.base_year)?.url
  return (
    <Item name="계속기업 불확실성" noteKey="going_concern" verdict={verdictOf(row)}>
      <Why row={row} />
      {c && (
        <>
          <p>
            {c.verdict === 'clear' ? '감사보고서에 계속기업 관련 중요한 불확실성이 보고되지 않았습니다.' : '감사보고서에 계속기업 관련 중요한 불확실성이 보고되었습니다. 원문에서 내용을 확인하세요.'}{' '}
            {c.basis === 'ai' ? <AiBadge task="extract_going_concern" kind="extract" /> : <span className={styles.sub}>(감사보고서 강조사항에서 코드가 확인)</span>} <Link url={link} />
          </p>
          <p className={styles.quote}>원문 인용: {c.quote}</p>
        </>
      )}
    </Item>
  )
}

function Corrections() {
  const { e } = useAi()
  const row = e.corrections
  const c = useContent('corrections')
  return (
    <Item name="정정공시" noteKey="corrections" verdict={verdictOf(row)}>
      <Why row={row} />
      {c && (
        <>
          <p>
            {c.period_start} ~ {c.period_end} 정기공시(사업·반기·분기보고서) 중 정정공시 <b>{c.count}건</b>
            {c.count === 0 ? ' — 없음' : ''}
          </p>
          {c.items.length > 0 && (
            <>
              <ul>{c.items.map((it) => <li key={it.url}>{it.date} · {it.title} <Link url={it.url} /></li>)}</ul>
              <p className={styles.muted}>정정은 단순 오기 수정도 많습니다. 무엇이 바뀌었는지는 원문에서 확인하세요.</p>
            </>
          )}
        </>
      )}
    </Item>
  )
}

function TextAmountsLine({ label, t }: { label: string; t: TextAmounts }) {
  if (t.state === 'none') return <p>{label}: <b>해당 없음</b> <span className={styles.sub}>(AI 추출 결과라 원문에서 누락됐을 수 있습니다)</span></p>
  if (t.state === 'unverified') return <p>{label}: <span className={styles.muted}>확인 불가(AI가 찾았지만 원문과 대조하지 못함)</span></p>
  return (
    <p>
      {label}: {t.items.map((i) => `${i.party ? i.party + ' ' : ''}${i.amount_text}`).join(', ')}
    </p>
  )
}

function RelatedParty({ r }: { r: ReportDetail }) {
  const { e } = useAi()
  const row = e.extract_related_party
  const c = useContent('extract_related_party')
  const link = r.sources.find((s) => s.kind === 'annual_report' && s.year === r.base_year)?.url
  return (
    <Item name="특수관계자 거래" noteKey="related_party" verdict={verdictOf(row)}>
      <Why row={row} />
      {c && (
        <>
          <p>
            <AiBadge task="extract_related_party" kind="extract" /> 연결 매출액 대비: 특수관계자 매출 등{' '}
            <b>{formatWonCard(c.sales_total_won).text}</b> ({formatPercent(c.sales_ratio).text}), 매입 등{' '}
            <b>{formatWonCard(c.purchases_total_won).text}</b> ({formatPercent(c.purchases_ratio).text}) <Link url={link} />
          </p>
          {c.verdict === 'unknown' && <p className={styles.muted}>합계 행을 원문과 대조하지 못한 항목이 있어 판정하지 못했습니다.</p>}
          <p className={styles.sub}>
            {Math.round(c.threshold * 100)}%는 이 도구의 참고 기준입니다(법적 기준 아님). 매출 또는 매입 합계가 연결 매출액의 {Math.round(c.threshold * 100)}% 이상이면 ‘확인 필요’로 표시합니다.
          </p>
          {c.top.length > 0 && (
            <>
              <p className={styles.muted}>금액이 큰 거래</p>
              <ul>{c.top.map((t) => <li key={t.party + t.kind}>{t.party} · {t.kind} {formatWonCard(t.amount_won).text}</li>)}</ul>
            </>
          )}
          <p className={styles.muted}>아래 두 항목은 판정하지 않고 금액만 보여 줍니다 (원문 표기 그대로, 통화 환산 없음).</p>
          <TextAmountsLine label="특수관계자 자금 대여금" t={c.loans} />
          <TextAmountsLine label="특수관계자 지급보증" t={c.guarantees} />
          {(c.loans.state === 'found' || c.guarantees.state === 'found') && <p>원문: <Link url={link}>{r.base_year} 사업보고서 · 재무제표 주석(특수관계자)</Link></p>}
        </>
      )}
    </Item>
  )
}

export function Accounting({ r }: { r: ReportDetail }) {
  const { e, running, rerun } = useAi()
  const none = !e.audit_opinion && !e.corrections && !e.extract_going_concern && !e.extract_related_party
  return (
    <SectionCard sectionKey="accounting">
      <h3>회계 이슈 체크</h3>
      <Summary sectionKey="accounting" />
      {none && !running && (
        <p className={styles.notice}>
          이 리포트에는 회계 이슈 체크가 아직 없습니다. <button className={styles.link} onClick={rerun}>AI 해석 만들기</button>
          <span className={styles.sub}> 누르면 감사의견·공시 목록을 조회하고 AI를 호출합니다 (이미 만든 해석은 다시 만들지 않습니다).</span>
        </p>
      )}
      <Audit />
      <GoingConcern r={r} />
      <Corrections />
      <RelatedParty r={r} />
    </SectionCard>
  )
}
