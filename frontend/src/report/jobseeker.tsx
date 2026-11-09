// 취업 준비생 질문 구성 (2026-11-03): "업계에서 어떤 위치예요? · 최근 보고서에서 새로 밝힌 것 · 앞으로 어디로 가요? · 일하기 어떤 회사예요? · 조심할 건 없어요?"
// 숫자는 코드가 계산한 값, 글은 사업보고서 PDF·DART 공시에서 AI가 뽑고 코드가 원문과 대조한 것만 보여 준다.
// 네이버 기사는 약관(가공·AI 입력 금지) 때문에 여기서 쓰지 않는다.
import type { ReactNode } from 'react'
import type { ChecklistItem, MarketShare, PdfPart, PdfQuote } from '../api'
import styles from '../app.module.css'
import { formatPercent, formatWonCard } from '../format/number'
import { Num } from '../ui'
import { AiBadge } from './ai'
import { useAi, useContent, useNotice } from './aiData'
import { SectionCard } from './comments'
import type { SectionKey } from './sectionKeys'

function Card({ sectionKey, title, unit, children }: { sectionKey: SectionKey; title: string; unit?: string; children: ReactNode }) {
  return (
    <SectionCard sectionKey={sectionKey}>
      <h3>{title} {unit && <span className={styles.unit}>{unit}</span>}</h3>
      {children}
    </SectionCard>
  )
}

/** 원문 인용: 회색 글씨 + "2025 사업보고서 p.42" 링크 */
export function Quotes({ quotes, max = 3 }: { quotes: PdfQuote[]; max?: number }) {
  if (quotes.length === 0) return null
  return (
    <ul className={styles.quotes}>
      {quotes.slice(0, max).map((q) => (
        <li key={q.cite + q.text.slice(0, 20)}>
          <span className={styles.quotetext}>“{q.text}”</span>{' '}
          {q.url ? <a className={styles.cite} href={q.url} target="_blank" rel="noreferrer">{q.cite}</a> : <span className={styles.cite}>{q.cite}</span>}
        </li>
      ))}
    </ul>
  )
}

function Missing({ task, what }: { task: Parameters<typeof useNotice>[0]; what: string }) {
  const notice = useNotice(task)
  const { report } = useAi()
  const noPdf = (report.pdfs ?? []).length === 0
  return (
    <p className={styles.muted}>
      {noPdf ? `보고서 원문을 읽는 기능이 생기기 전에 만든 리포트라 ${what}을(를) 보여 줄 수 없습니다. 리포트를 새로 만들어 주세요.` : notice?.message ?? `${what} 자료가 아직 없습니다`}
    </p>
  )
}

/** 요약 한 단락 + 원문 인용 */
function Part({ title, part, task }: { title: string; part: PdfPart | null | undefined; task: 'extract_focus' | 'extract_mda' }) {
  if (!part || (!part.summary && part.quotes.length === 0)) return null
  return (
    <div className={styles.part}>
      <div className={styles.parttitle}>{title}</div>
      {part.summary && <p className={styles.parttext}>{part.summary} <AiBadge task={task} kind="extract" /></p>}
      <Quotes quotes={part.quotes} />
    </div>
  )
}

// ───────────────────────── 업계에서 어떤 위치예요?
export function Industry() {
  const c = useContent('extract_position')
  const pos = c?.position
  const shares = pos?.market_shares ?? []
  return (
    <Card sectionKey="industry" title="업계 안에서의 위치" unit="(사업보고서 기준)">
      <p className={styles.sub}>회사가 공시한 제품·시장별 위치입니다. 시장의 범위, 조사 기간과 출처를 함께 확인하세요.</p>
      {!c ? <Missing task="extract_position" what="업계 위치" /> : (
        <>
          {pos?.summary && <p>{pos.summary} <AiBadge task="extract_position" kind="extract" /></p>}
          {shares.length > 0 && (
            <div className={styles.part}>
              <div className={styles.parttitle}>시장점유율 — 전체 시장에서 이 회사가 차지하는 몫</div>
              {shares.map((m) => <ShareBar key={m.product} m={m} />)}
              <p className={styles.footnote}>
                점유율 값과 기간은 사업보고서 원문 표에서 옮긴 것을 코드가 원문과 대조했습니다. 막대의 회색 부분(그 밖의 회사)은 100%에서 뺀 값입니다(코드 계산).
                {shares.some((m) => m.source) && <> 원 자료: {[...new Set(shares.map((m) => m.source).filter(Boolean))].join(', ')} (회사가 밝힌 출처)</>}
              </p>
            </div>
          )}
          {pos && pos.quotes.length > 0 && (
            <div className={styles.part}>
              <div className={styles.parttitle}>시장점유율·업계 위치 (원문)</div>
              <Quotes quotes={pos.quotes} />
              <p className={styles.footnote}>표에서 옮긴 줄은 숫자만 이어져 보일 수 있습니다. 연도 순서와 단위는 원문 링크에서 확인해 주세요.</p>
            </div>
          )}
          {!pos && <p className={styles.muted}>사업보고서에 업계 위치나 시장점유율 언급이 없습니다.</p>}
        </>
      )}
    </Card>
  )
}

function ShareBar({ m }: { m: MarketShare }) {
  const pct = Math.max(0, Math.min(100, m.share * 100))
  const rest = Math.round((100 - pct) * 10) / 10
  const period = m.periods[0]
  return (
    <div className={styles.sharerow}>
      <div className={styles.sharehead}>
        <b>{m.product}</b> <span className={styles.sharevalue}>{m.values[0]}</span>
        {period && <span className={styles.sub}> ({period} 기준)</span>}
      </div>
      <div className={styles.sharebar} role="img" aria-label={`${m.product} 점유율 ${m.values[0]}, 그 밖의 회사 ${rest}%`}>
        <div className={styles.sharemine} style={{ width: `${pct}%` }}>이 회사</div>
        <div className={styles.sharerest}>그 밖의 회사 {rest}%</div>
      </div>
      {m.periods.length > 1 && (
        <div className={styles.sharehist}>
          {m.periods.map((p, i) => <span key={p}>{p} <b>{m.values[i]}</b></span>)}
        </div>
      )}
    </div>
  )
}

// ───────────────────────── 최근 보고서에서 새로 밝힌 내용
export function Interests() {
  const focus = useContent('extract_focus')
  const changes = focus?.changes
  const recent = [
    changes?.rnd && (changes.rnd.text || changes.rnd.quotes.length > 0) ? { title: '최근 연구개발 성과', ...changes.rnd } : null,
    changes?.investment && (changes.investment.text || changes.investment.quotes.length > 0) ? { title: '최근 투자', ...changes.investment } : null,
  ].filter((x): x is NonNullable<typeof x> => x !== null)
  if (recent.length === 0) return null
  return (
    <Card sectionKey="topics" title="최근 보고서에서 새로 밝힌 내용" unit={focus?.interim_label ?? undefined}>
      {recent.map((x) => (
        <div key={x.title} className={styles.subpart}>
          <b>{x.title}</b>{x.text && <> — {x.text} <AiBadge task="extract_focus" kind="extract" /></>}
          <Quotes quotes={x.quotes} />
        </div>
      ))}
    </Card>
  )
}

// ───────────────────────── 앞으로 어디로 가요?
export function Future() {
  const focus = useContent('extract_focus')
  const rnd = useContent('extract_rnd')
  return (
    <Card sectionKey="future" title="회사가 밝힌 방향" unit="(신사업·연구개발·투자)">
      {!focus ? <Missing task="extract_focus" what="회사의 방향" /> : (
        <>
          <Part title="새로 키우는 사업" part={focus.new_business} task="extract_focus" />
          <Part title="연구개발" part={focus.rnd} task="extract_focus" />
          {rnd && (
            <p className={styles.sub}>
              연구개발비 <b><Num f={formatWonCard(rnd.amount_won)} /></b>
              {rnd.ratio_to_revenue !== null && <> · 매출의 {formatPercent(rnd.ratio_to_revenue).text}</>} (계산은 코드)
            </p>
          )}
          <Part title="투자" part={focus.investment} task="extract_focus" />
        </>
      )}
    </Card>
  )
}

/** 실적 탭: 경영진이 직접 설명한 실적의 이유 (사업보고서 IV. 이사의 경영진단 및 분석의견, 2026-11-04 회사의 방향에서 분리) */
export function Mda() {
  const mda = useContent('extract_mda')
  return (
    <Card sectionKey="mda" title="경영진이 설명한 실적" unit="(사업보고서 IV. 경영진단)">
      {!mda ? <Missing task="extract_mda" what="경영진단" /> : <Part title="지난해 실적과 재무 상태, 앞으로" part={mda} task="extract_mda" />}
    </Card>
  )
}

// ───────────────────────── 조심할 건 없어요?
const STATUS: Record<ChecklistItem['status'], { label: string; cls: string }> = {
  check: { label: '확인 필요', cls: styles.warn },
  clear: { label: '이상 없음', cls: styles.good },
  info: { label: '참고', cls: styles.sub },
  unknown: { label: '확인 불가', cls: styles.sub },
}

export function Caution() {
  const c = useContent('checklist')
  const pos = useContent('extract_position')
  const risks = pos?.risks ?? []
  return (
    <Card sectionKey="caution" title="주의해서 볼 것">
      {!c ? <Missing task="checklist" what="체크리스트" /> : (
        <ul className={styles.checklist}>
          {c.items.map((it) => (
            <li key={it.key}>
              <span className={`${styles.checkstatus} ${STATUS[it.status].cls}`}>{STATUS[it.status].label}</span>
              <span className={styles.checklabel}>{it.label}</span>
              <span className={styles.checkreason}>
                {it.reasons.join(' · ')}
                {it.key === 'dependence' && it.status === 'check' && c.concentration_note && <span className={styles.footnote}> ({c.concentration_note})</span>}
              </span>
            </li>
          ))}
        </ul>
      )}
      {risks.length > 0 && (
        <div className={styles.part}>
          <div className={styles.parttitle}>회사가 직접 밝힌 위험</div>
          <ul className={styles.risklist}>
            {risks.map((x) => (
              <li key={x.quote.cite + x.quote.text.slice(0, 20)}>
                {x.plain && <>{x.plain} <AiBadge task="extract_position" kind="extract" /></>}
                <Quotes quotes={[x.quote]} />
              </li>
            ))}
          </ul>
        </div>
      )}
      {c?.note && <p className={styles.footnote}>{c.note}. 판정 기준과 계산은 코드가 정하고, AI는 쓰지 않습니다.</p>}
    </Card>
  )
}
