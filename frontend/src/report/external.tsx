// 7-B AI 해석 화면: 1장 종합 한 줄 평가, 2장 공시 주제, 3장 SWOT·과제, 4장 직무별 기여·예상 면접 질문, 부록 A PEST·민감도, 부록 B 5 Forces
// 근거 이름·링크, 공시 날짜·링크, 과제 근거 섹션 이름은 백엔드 코드가 붙인 값을 쓴다 (AI가 쓰지 않음).
// 리포트 안 섹션 이름은 근거 키를 보고 새 위치(1~4장·부록)로 바꿔 보여주고, 누르면 그 섹션으로 이동한다 (format/places).
import type { ReactNode } from 'react'
import type { Enrichments, ExternalContent, RoleKey, SourceIndex, SourcedItem } from '../api'
import styles from '../app.module.css'
import { formatExchangeRate, formatPercent, formatChange } from '../format/number'
import { AiBadge, Summary } from './ai'
import { TOPIC_MARK, useAi, useContent, useNotice } from './aiData'
import { placeOf } from '../format/places'
import { SectionCard } from './comments'
import { JumpLink } from './fold'
import type { SectionKey } from './sectionKeys'

/** 작업이 없거나 실패·자료 없음일 때 섹션 안내 */
function Missing({ task }: { task: keyof Enrichments }) {
  const { e } = useAi()
  const notice = useNotice(task)
  if (!(task in e)) return <p className={styles.muted}>아직 만들지 않았습니다. 리포트 맨 위 안내의 버튼을 누르면 만듭니다.</p>
  return <p className={styles.muted}>{notice?.message ?? '자료 없음'}</p>
}

/** 근거 이름 하나: 리포트 안 섹션이면 그 섹션으로 이동, 원문 자료면 원문 링크 */
function Basis({ k, label, url }: { k: string; label: string; url?: string | null }) {
  const p = placeOf(k, label)
  if (p.target) return <JumpLink to={p.target}>{p.label}</JumpLink>
  return url ? <a href={url} target="_blank" rel="noreferrer">{p.label}</a> : <>{p.label}</>
}

/** 항목 뒤의 근거 표시: 이름(링크) */
export function SourceTags({ keys, index }: { keys: string[]; index: SourceIndex }) {
  return (
    <span className={styles.srctags}>
      근거:{' '}
      {keys.map((k, i) => (
        <span key={k}>
          {i > 0 && ', '}
          <Basis k={k} label={index[k]?.label ?? k} url={index[k]?.url} />
        </span>
      ))}
    </span>
  )
}

function ItemList({ items, index }: { items: SourcedItem[]; index: SourceIndex }) {
  if (items.length === 0) return <p className={styles.muted}>자료 없음</p>
  return (
    <ul className={styles.itemlist}>
      {items.map((it) => (
        <li key={it.text}>{it.text} <SourceTags keys={it.sources} index={index} /></li>
      ))}
    </ul>
  )
}

function Card({ sectionKey, title, unit, top, children }: { sectionKey: SectionKey; title: string; unit?: string; top?: ReactNode; children: ReactNode }) {
  return (
    <SectionCard sectionKey={sectionKey}>
      <h3>{title} {unit && <span className={styles.unit}>{unit}</span>}</h3>
      {top}
      <Summary sectionKey={sectionKey} />
      {children}
    </SectionCard>
  )
}

// ───────────────────────── 1장: 종합 한 줄 평가 (SWOT과 같은 AI 호출, 코멘트란 없음)
export function Verdict() {
  const c = useContent('write_swot')
  if (!c) return <Missing task="write_swot" />
  if (!c.verdict) return null
  return <p className={styles.verdict}><AiBadge task="write_swot" /> {c.verdict}</p>
}

// ───────────────────────── 3장: SWOT
const SWOT_LABEL = { strengths: '강점 (S)', weaknesses: '약점 (W)', opportunities: '기회 (O)', threats: '위협 (T)' } as const

export function Swot() {
  const c = useContent('write_swot')
  return (
    <Card sectionKey="swot" title="SWOT" unit="(1·2장과 부록 분석 기반)">
      {!c ? <Missing task="write_swot" /> : (
        <div className={styles.grid2}>
          {(Object.keys(SWOT_LABEL) as (keyof typeof SWOT_LABEL)[]).map((k) => (
            <div key={k} className={styles.box}>
              <div className={styles.boxtitle}>{SWOT_LABEL[k]} <AiBadge task="write_swot" /></div>
              <ItemList items={c.swot[k]} index={c.source_index} />
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}

// ───────────────────────── 부록 A: PEST
const PEST_LABEL = { politics: '정책 (P)', economy: '경제 (E)', society: '사회 (S)', technology: '기술 (T)' } as const

export function Pest() {
  const c = useContent('write_external')
  return (
    <Card sectionKey="pest" title="PEST">
      {!c ? <Missing task="write_external" /> : (
        <div className={styles.grid2}>
          {(Object.keys(PEST_LABEL) as (keyof typeof PEST_LABEL)[]).map((k) => (
            <div key={k} className={styles.box}>
              <div className={styles.boxtitle}>{PEST_LABEL[k]} <AiBadge task="write_external" /></div>
              <ItemList items={c.pest[k] ?? []} index={c.source_index} />
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}

// ───────────────────────── 부록 B: 5 Forces
const STRENGTH_TONE = { 강: 'bad', 중: 'warn', 약: 'good' } as const

export function FiveForces() {
  const c = useContent('write_external')
  return (
    <Card sectionKey="five_forces" title="5 Forces" unit="(요인별 강도: 강·중·약)">
      {!c ? <Missing task="write_external" /> : c.five_forces.length === 0 ? <p className={styles.muted}>자료 없음</p> : (
        <table className={`${styles.table} ${styles.forces}`}>
          <thead><tr><th>요인</th><th className={styles.left}>강도</th><th className={styles.left}>근거 <AiBadge task="write_external" /></th></tr></thead>
          <tbody>
            {c.five_forces.map((f) => (
              <tr key={f.key}>
                <td>{f.name}</td>
                <td className={styles.left}><span className={`${styles.signal} ${styles[STRENGTH_TONE[f.strength]]}`}>{f.strength}</span></td>
                <td className={styles.left}>{f.reason} <SourceTags keys={f.sources} index={c.source_index} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className={styles.footnote}>강도는 이 회사가 받는 압력의 크기입니다(강할수록 수익성에 부담).</p>
    </Card>
  )
}

// ───────────────────────── 2장: 공시 주제 묶음
export function Topics() {
  const c = useContent('write_external')
  const p = c?.disclosure_period
  return (
    <Card sectionKey="topics" title="공시 주제 묶음" unit={p?.period_start ? `(DART 공시 ${p.period_start} ~ ${p.period_end}, ${p.total}건)` : undefined}>
      {!c ? <Missing task="write_external" /> : c.topics.length === 0 ? <p className={styles.muted}>최근 3개월 공시가 없거나 묶을 만한 공시가 없습니다</p> : (
        <div className={styles.grid3}>
          {c.topics.map((t, i) => (
            <div key={t.title} className={styles.box}>
              <div className={styles.boxtitle}>{TOPIC_MARK[i]} {t.title} <AiBadge task="write_external" /></div>
              <p className={styles.small}>{t.summary}</p>
              <ul className={styles.disclist}>
                {t.disclosures.map((d) => (
                  <li key={d.rcept_no}><span className={styles.sub}>{d.date}</span> <a href={d.url} target="_blank" rel="noreferrer">{d.title}</a></li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
      <p className={styles.footnote}>
        DART 공시 제목·접수일만 보고 묶었습니다(공시 본문은 원문 링크에서 확인). 공시 날짜는 <JumpLink to="stocks">부록 D 주가 흐름 차트</JumpLink>에 번호로 표시됩니다.
        네이버 기사는 약관상 AI 분석에 쓰지 않습니다.
      </p>
    </Card>
  )
}

// ───────────────────────── 부록 A: 경제 환경 민감도 (환율·기준금리 섹션 안)
const DIR_TONE: Record<string, string> = { 긍정: 'good', 부정: 'bad', 혼재: 'warn', '자료 없음': 'unknown' }

export function Sensitivity() {
  const c = useContent('write_external')
  if (!c) return <Missing task="write_external" />
  const s: ExternalContent['sensitivity'] = c.sensitivity
  if (!s.available) return <p className={styles.muted}>환율 10% 상승 시 영향: 자료 없음 (수출 비중 또는 환율 자료가 없습니다)</p>
  return (
    <>
      <p className={styles.tabletitle}>환율 10% 상승 시 영향 방향 <AiBadge task="write_external" /></p>
      <table className={styles.table}>
        <tbody>
          <tr><td>수출(해외 매출) 비중</td><td className={styles.left}>{formatPercent(s.export_share).text}</td></tr>
          <tr><td>원/달러 환율 1년 변화</td><td className={styles.left}>{s.fx && <>{formatExchangeRate(s.fx.start).text} → {formatExchangeRate(s.fx.end).text} ({formatChange(s.fx.change).text})</>}</td></tr>
          {(['revenue', 'cost'] as const).map((side) => {
            const v = s[side]
            return (
              <tr key={side}>
                <td>{side === 'revenue' ? '매출' : '원가'}</td>
                <td className={styles.left}>
                  {v ? <><span className={`${styles.signal} ${styles[DIR_TONE[v.direction]]}`}>{v.direction}</span> {v.reason}</> : '자료 없음'}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
      {s.sources && <p className={styles.footnote}><SourceTags keys={s.sources} index={c.source_index} /> · 방향과 이유만 쓰며 금액은 추정하지 않습니다. 비중·환율 변화는 코드 계산.</p>}
    </>
  )
}

// ───────────────────────── 4장: 예상 면접 질문 (기존 지켜볼 점·생각해볼 질문, 질문을 앞에. AI 호출·프롬프트 그대로)
export function Interview() {
  const c = useContent('write_external')
  return (
    <Card sectionKey="watch" title="예상 면접 질문" top={<p className={styles.sub}>분석에서 뽑은 질문이며 실제 면접 질문이 아닙니다.</p>}>
      {!c ? <Missing task="write_external" /> : (
        <div className={styles.grid2}>
          <div className={styles.box}>
            <div className={styles.boxtitle}>생각해볼 질문 <AiBadge task="write_external" /></div>
            <ItemList items={c.watch.questions} index={c.source_index} />
          </div>
          <div className={styles.box}>
            <div className={styles.boxtitle}>앞으로 확인할 점 <AiBadge task="write_external" /></div>
            <ItemList items={c.watch.checks} index={c.source_index} />
          </div>
        </div>
      )}
    </Card>
  )
}

// ───────────────────────── 3장 과제·역량 / 4장 직무별 기여 (같은 AI 호출 write_page4)
const ROLE_LABEL: Record<RoleKey, string> = { fpa: 'FP&A', accounting: '재무회계', treasury: '자금', research: '리서치' }

function SuggestNotice() {
  return (
    <p className={styles.notice}>
      <span className={styles.suggestbadge}>분석 기반 제안</span> <AiBadge task="write_page4" />{' '}
      분석 기반 제안입니다. 회사의 공식 인재상이 아닙니다.
    </p>
  )
}

function FewTasks({ count }: { count: number }) {
  if (count >= 3) return null
  return <p className={styles.muted}>근거 부족: 리포트 분석에서 근거가 확인된 과제 {count}개만 보여줍니다.</p>
}

export function Tasks() {
  const c = useContent('write_page4')
  return (
    <Card sectionKey="tasks" title="회사의 과제와 필요한 역량" top={<SuggestNotice />}>
      {!c ? <Missing task="write_page4" /> : (
        <>
          <FewTasks count={c.tasks.length} />
          <div className={styles.grid3}>
            {c.tasks.map((t, i) => (
              <div key={t.title} className={styles.box}>
                <div className={styles.boxtitle}>과제 {i + 1}. {t.title}</div>
                {t.detail && <p className={styles.small}>{t.detail}</p>}
                <p className={styles.sub}>근거: {t.basis.map((b, j) => <span key={b.key}>{j > 0 && ', '}<Basis k={b.key} label={b.label} /></span>)}</p>
                <p className={styles.small}><b>필요한 역량</b> {t.capability ?? '자료 없음'}</p>
              </div>
            ))}
          </div>
          <p className={styles.footnote}>과제·역량은 AI가 리포트 분석 결과 안에서만 쓴 짧은 아이디어이며, 근거 섹션 이름은 코드가 붙입니다. 자기소개서 문장은 쓰지 않습니다.</p>
        </>
      )}
    </Card>
  )
}

export function RoleIdeas() {
  const c = useContent('write_page4')
  const roles = Object.keys(ROLE_LABEL) as RoleKey[]
  return (
    <Card sectionKey="page4" title="직무별 기여 아이디어" unit="(3장 과제 × 직무)" top={<SuggestNotice />}>
      {!c ? <Missing task="write_page4" /> : (
        <>
          <FewTasks count={c.tasks.length} />
          {c.tasks.length > 0 && (
            <div className={styles.tablescroll}>
              <table className={`${styles.table} ${styles.roles}`}>
                <thead><tr><th className={styles.left}>과제</th>{roles.map((k) => <th key={k} className={styles.left}>{ROLE_LABEL[k]} <AiBadge task="write_page4" /></th>)}</tr></thead>
                <tbody>
                  {c.tasks.map((t, i) => (
                    <tr key={t.title}>
                      <td className={styles.left}><b>과제 {i + 1}.</b> {t.title}</td>
                      {roles.map((k) => <td key={k} className={styles.left}>{t.ideas[k] ?? <span className={styles.muted}>자료 없음</span>}</td>)}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className={styles.footnote}>기여 아이디어는 AI가 리포트 분석 결과 안에서만 쓴 짧은 아이디어입니다. 자기소개서 문장은 쓰지 않습니다.</p>
        </>
      )}
    </Card>
  )
}
