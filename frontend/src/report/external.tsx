// 7-B AI 해석 화면: 1장 종합 한 줄 평가, 2장 공시 주제, 3장 SWOT·과제, 4장 직무별 기여·예상 면접 질문, 부록 A PEST·민감도, 부록 B 5 Forces
// 근거 이름·링크, 공시 날짜·링크, 과제 근거 섹션 이름은 백엔드 코드가 붙인 값을 쓴다 (AI가 쓰지 않음).
// 리포트 안 섹션 이름은 근거 키를 보고 새 위치(1~4장·부록)로 바꿔 보여주고, 누르면 그 섹션으로 이동한다 (format/places).
import type { ReactNode } from 'react'
import type { Enrichments, ExternalContent, SourceIndex, SourcedItem } from '../api'
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

function ItemList({ items, index, compact = false }: { items: SourcedItem[]; index: SourceIndex; compact?: boolean }) {
  if (items.length === 0) return <p className={styles.muted}>자료 없음</p>
  return (
    <ul className={styles.itemlist}>
      {items.map((it) => (
        <li key={it.text}>{it.text}{!compact && <> <SourceTags keys={it.sources} index={index} /></>}</li>
      ))}
    </ul>
  )
}

/** 간결 모드(2026-11-04 PEST·SWOT): 항목마다 근거를 달지 않고 카드 아래에 한 번만 모아 보여 준다 */
function AllSources({ lists, index }: { lists: SourcedItem[][]; index: SourceIndex }) {
  const keys = [...new Set(lists.flat().flatMap((it) => it.sources))]
  if (keys.length === 0) return null
  return <p className={styles.footnote}><SourceTags keys={keys} index={index} /></p>
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
    <Card sectionKey="swot" title="SWOT" unit="(앞의 분석 기반)">
      {!c ? <Missing task="write_swot" /> : (
        <div className={styles.grid2}>
          {(Object.keys(SWOT_LABEL) as (keyof typeof SWOT_LABEL)[]).map((k) => (
            <div key={k} className={styles.box}>
              <div className={styles.boxtitle}>{SWOT_LABEL[k]}</div>
              <ItemList items={c.swot[k]} index={c.source_index} compact />
            </div>
          ))}
        </div>
      )}
      {c && <><AiBadge task="write_swot" /> <AllSources lists={Object.values(c.swot)} index={c.source_index} /></>}
    </Card>
  )
}

// ───────────────────────── 부록 A: PEST
const PEST_LABEL = { politics: '정책 (P)', economy: '경제 (E)', society: '사회 (S)', technology: '기술 (T)' } as const
const PEST_GUIDE = {
  politics: '법·규제와 정부 정책 변화',
  economy: '경기·금리·환율 등 경제 여건',
  society: '인구·생활 방식과 고객 수요 변화',
  technology: '기술 발전과 기존 제품의 변화 가능성',
} as const

export function Pest() {
  const c = useContent('write_external')
  return (
    <Card sectionKey="pest" title="PEST" top={<p className={styles.sub}>회사가 통제하기 어려운 정책·경제·사회·기술 변화가 업계에 미칠 영향을 살펴봅니다.</p>}>
      {!c ? <Missing task="write_external" /> : (
        <div className={styles.grid2}>
          {(Object.keys(PEST_LABEL) as (keyof typeof PEST_LABEL)[]).map((k) => (
            <div key={k} className={styles.box}>
              <div className={styles.boxtitle}>{PEST_LABEL[k]}</div>
              <p className={styles.sub}>{PEST_GUIDE[k]}</p>
              <ItemList items={c.pest[k] ?? []} index={c.source_index} compact />
            </div>
          ))}
        </div>
      )}
      {c && <><AiBadge task="write_external" /> <AllSources lists={Object.values(c.pest).map((x) => x ?? [])} index={c.source_index} /></>}
    </Card>
  )
}

// ───────────────────────── 부록 B: 5 Forces
const STRENGTH_TONE = { 강: 'bad', 중: 'warn', 약: 'good' } as const
const FORCE_GUIDE: Record<string, string> = {
  rivalry: '기존 업체끼리 가격·기술·품질을 두고 벌이는 경쟁',
  new_entrants: '새 회사가 시장에 들어오기 쉬운 정도',
  substitutes: '다른 제품이나 기술이 수요를 대신할 가능성',
  supplier_power: '원재료·부품 공급업체가 가격과 조건에 미치는 영향',
  buyer_power: '고객이 가격·품질·납품 조건에 미치는 영향',
}

export function FiveForces() {
  const c = useContent('write_external')
  return (
    <Card sectionKey="five_forces" title="5 Forces" unit="(요인별 강도: 강·중·약)"
      top={<p className={styles.sub}>다섯 가지 업계 압력이 회사의 수익성에 얼마나 부담이 되는지 봅니다.</p>}>
      {!c ? <Missing task="write_external" /> : c.five_forces.length === 0 ? <p className={styles.muted}>자료 없음</p> : (
        <table className={`${styles.table} ${styles.forces}`}>
          <thead><tr><th>요인</th><th className={styles.left}>강도</th><th className={styles.left}>근거 <AiBadge task="write_external" /></th></tr></thead>
          <tbody>
            {c.five_forces.map((f) => (
              <tr key={f.key}>
                <td>{f.name}<div className={styles.sub}>{FORCE_GUIDE[f.key]}</div></td>
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
        DART 공시 제목·접수일만 보고 묶었습니다(공시 본문은 원문 링크에서 확인). 공시 날짜는 <JumpLink to="stocks">주가 흐름 비교</JumpLink>에 번호로 표시됩니다.
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
  // 2026-11-04: 결제 통화 자료가 없어 매출·원가 방향이 모두 '자료 없음'이면 표를 보이지 않는다(환율·금리 차트는 그대로)
  if (!s.available || (!s.revenue && !s.cost)) return null
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
