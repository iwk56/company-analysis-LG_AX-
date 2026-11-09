// 사업 구조 탭 (2026-11-04): 무엇을 팔고(제품·가격) · 어디서 벌고(매출 구성·고객) · 어느 사업이 남기고(부문 손익)
// · 얼마나 만들고(생산·가동률) · 무엇으로 만드는지(원재료) · 앞으로 확보된 매출(수주) · 어떤 회사들을 거느리는지(출자 회사).
// 글은 사업보고서 원문에서 AI가 뽑고 코드가 원문과 대조한 인용만, 출자 회사는 OpenDART 값을 코드가 정리한다.
import type { ReactNode } from 'react'
import type { BusinessWebItem, PdfPart } from '../api'
import styles from '../app.module.css'
import { formatPercent, formatWonTable } from '../format/number'
import { Num } from '../ui'
import { AiBadge } from './ai'
import { useAi, useContent, useNotice } from './aiData'
import { Quotes } from './jobseeker'
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

const PARTS: { key: 'products' | 'sales_mix' | 'segments' | 'production' | 'materials' | 'orders'; title: string; why: string }[] = [
  { key: 'products', title: '무엇을 파나 · 가격 흐름', why: '주력 제품과 매출 비중, 제품 가격이 오르는지' },
  { key: 'sales_mix', title: '어디서 파나', why: '내수·수출, 지역, 판매 경로' },
  { key: 'segments', title: '어느 사업이 이익을 내나', why: '사업부문별 매출·영업이익, 큰 고객' },
  { key: 'production', title: '얼마나 만드나', why: '생산능력·생산실적·가동률' },
  { key: 'materials', title: '무엇으로 만드나', why: '주요 원재료와 원가를 움직이는 요인' },
  { key: 'orders', title: '앞으로 확보된 매출', why: '수주 현황(수주 산업일 때 중요)' },
]

const MAX_BUSINESS_QUOTES = 3

function Part({ title, why, part, note }: { title: string; why: string; part: PdfPart | null | undefined; note?: ReactNode }) {
  return (
    <div className={styles.bizpart}>
      <div className={styles.parttitle}>{title} <span className={styles.sub}>{why}</span></div>
      {!part && !note ? <p className={styles.muted}>보고서에 이 내용이 없거나 원문과 대조되지 않았습니다.</p> : (
        <>
          {part?.summary && <p className={styles.parttext}>{part.summary} <AiBadge task="extract_business" kind="extract" /></p>}
          {part && part.quotes.length > 0 && (
            <details className={styles.businessEvidence}>
              <summary>원문 근거 {Math.min(part.quotes.length, MAX_BUSINESS_QUOTES)}개 보기</summary>
              <Quotes quotes={part.quotes} max={MAX_BUSINESS_QUOTES} />
            </details>
          )}
          {note}
        </>
      )}
    </div>
  )
}

export function BusinessStructure() {
  const c = useContent('extract_business')
  const notice = useNotice('extract_business')
  const pos = useContent('extract_position')
  const seg = useContent('extract_segments')
  const web = useContent('web_news')
  const businessWeb = useContent('business_web')
  const businessWebNotice = useNotice('business_web')
  const { report } = useAi()
  const customers = pos?.customers ?? []
  // 사업보고서 원문(II-4)에는 지역별 매출 비중이 잘 없지만, 연결재무제표 주석(지역별 매출)에서
  // extract_segments가 이미 원문 대조까지 마친 해외 매출 비중을 계산해 둔다. "어디서 파나"가 "자료 없음"이라고
  // 말해도, 같은 리포트 다른 곳에 이미 검증된 숫자가 있으면 그 숫자를 보여 준다 (2026-11-05).
  const overseasNote = seg?.overseas_share != null ? (
    <p className={styles.parttext}>
      참고: 연결재무제표 주석(지역별 매출)으로 계산하면 해외 매출 비중은 <b><Num f={formatPercent(seg.overseas_share)} /></b>입니다.
      <span className={styles.sub}> (국내를 뺀 값 · 코드가 계산 · 사업부문 비중과 같은 자료)</span>
    </p>
  ) : null
  // 제품 가격은 사업보고서에 거의 안 나온다. 실적 탭 '왜 이렇게 됐나'용으로 이미 돌린 웹 검색(web_news)이
  // price 단계로 분류해 둔 기사를 여기서도 보여 준다 — 새 AI 호출 없이 같은 결과를 재사용한다 (2026-11-05).
  const priceNews = (web?.items ?? []).filter((n) => n.step === 'price')
  const priceNote = priceNews.length > 0 ? (
    <div className={styles.newsbox}>
      <span className={styles.newslabel}>기사에서 찾은 가격 동향</span> <AiBadge task="web_news" />
      <ul>
        {priceNews.map((n) => (
          <li key={n.url}>{n.claim}{' '}
            <a href={n.url} target="_blank" rel="noreferrer">{n.publisher || '기사'}{n.date ? ` · ${n.date}` : ''} ↗</a>
          </li>
        ))}
      </ul>
      <p className={styles.footnote}>AI가 웹 검색(최대 3번)으로 찾은 기사이며, 실제로 검색된 주소만 남겼습니다. 기사 속 숫자는 이 리포트가 검증하지 않았습니다.</p>
    </div>
  ) : null
  const businessItems = businessWeb?.items ?? []
  const missingBusinessMessage = businessWebNotice
    ? businessWebNotice.message
    : (report.pdfs ?? []).length === 0
      ? '보고서 원문을 읽는 기능이 생기기 전에 만든 리포트입니다. 리포트를 새로 만들어 주세요.'
      : notice?.message ?? '사업 구조 자료가 아직 없습니다.'
  const businessNote = businessItems.length > 0 ? (
    <div className={styles.newsbox}>
      <span className={styles.newslabel}>공식 공시·회사 IR 웹 검색 보완</span> <AiBadge task="business_web" />
      <ul>
        {businessItems.map((item: BusinessWebItem) => (
          <li key={item.topic}>
            <b>{item.topic === 'region' ? '지역별 매출' : '판매 경로'}:</b> {item.claim}{' '}
            <a href={item.url} target="_blank" rel="noreferrer">{item.title} ({item.year} 사업연도) ↗</a>
          </li>
        ))}
      </ul>
      <p className={styles.footnote}>OpenAI 웹 검색 요약입니다. 링크는 DART 또는 OpenDART에서 확인한 회사 공식 홈페이지 도메인으로 검증했으며, 요약 수치는 재무 원문과 별도로 대조하지 않았습니다.</p>
    </div>
  ) : businessWebNotice ? (
    <p className={styles.muted}>{businessWebNotice.message}</p>
  ) : null
  return (
    <Card sectionKey="business" title="사업 구조" unit="(사업보고서 II장·영업부문 주석)">
      {!c && businessItems.length === 0 ? (
        <p className={styles.muted}>{missingBusinessMessage}</p>
      ) : (
        PARTS.map((p) => (
          <Part
            key={p.key}
            title={p.title}
            why={p.why}
            part={c?.[p.key]}
            note={p.key === 'sales_mix' ? <>{overseasNote}{businessNote}</> : p.key === 'products' ? priceNote : undefined}
          />
        ))
      )}
      {customers.length > 0 && (
        <div className={styles.bizpart}>
          <div className={styles.parttitle}>누구에게 파나 <span className={styles.sub}>보고서에 나온 주요 고객</span></div>
          <ul className={styles.itemlist}>
            {customers.map((x) => (
              <li key={x.quote.cite + x.quote.text.slice(0, 20)}>
                {x.share_text && <b>{x.share_text} </b>}
                <Quotes quotes={[x.quote]} />
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  )
}

export function Subsidiaries() {
  const s = useContent('subsidiaries')
  const notice = useNotice('subsidiaries')
  return (
    <Card sectionKey="subsidiaries" title="출자 회사 (자회사·관계회사)" unit={s ? `(${s.year} 사업보고서 · 장부가액 큰 순)` : undefined}>
      {!s ? <p className={styles.muted}>{notice?.message ?? '타법인 출자 현황이 아직 없습니다.'}</p> : (
        <>
          <p>지분을 가진 회사 <b>{s.count}곳</b>, 그중 지분 50% 이상(보통 종속회사) <b>{s.majority_count}곳</b></p>
          <div className={styles.tablewrap}>
            <table className={styles.table}>
              <thead>
                <tr><th>회사</th><th>출자 목적</th><th className={styles.num}>지분율</th><th className={styles.num}>장부가액(억 원)</th><th className={styles.num}>그 회사 순이익(억 원)</th></tr>
              </thead>
              <tbody>
                {s.items.map((x) => (
                  <tr key={x.name}>
                    <td>{x.name}</td>
                    <td className={styles.sub}>{x.purpose ?? '-'}</td>
                    <td className={styles.num}>{x.share !== null ? `${x.share.toFixed(1)}%` : '-'}</td>
                    <td className={styles.num}><Num f={formatWonTable(x.book_won)} /></td>
                    <td className={styles.num}><Num f={formatWonTable(x.net_income_won)} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className={styles.footnote}>
            OpenDART 「타법인 출자 현황」 값을 코드가 정리했습니다. 지분 50% 이상이어도 회계상 지배 여부는 원문에서 확인하세요.
            {s.count > s.items.length && ` 장부가액 상위 ${s.items.length}곳만 보여 줍니다.`}
            {s.url && <> <a href={s.url} target="_blank" rel="noreferrer">원문</a></>}
          </p>
        </>
      )}
    </Card>
  )
}

// ───────────────────────── 산업·경쟁 탭: 경쟁사와 비교한 해석 (2026-11-04)
const PEER_GROUPS: { key: 'strengths' | 'advantages' | 'weaknesses' | 'opportunities'; title: string; description: string; cls: string }[] = [
  { key: 'strengths', title: '실적상 강점', description: '비교 기업보다 높은 이익률·성장률 등', cls: styles.peergood },
  { key: 'advantages', title: '규모·재무 여력', description: '매출 규모나 부채 등 사업 운영 조건', cls: styles.peergood },
  { key: 'weaknesses', title: '비교에서 뒤처진 점', description: '경쟁사보다 낮거나 부담이 큰 지표', cls: styles.peerbad },
  { key: 'opportunities', title: '개선 여지', description: '비교 수치에서 보이는 격차 축소 가능성', cls: styles.peerinfo },
]

export function PeerInsight() {
  const c = useContent('write_peers')
  const notice = useNotice('write_peers')
  const { report } = useAi()
  const labels = Object.fromEntries((report.results.comparison?.columns ?? []).map((col) => [col.key, col.label]))
  return (
    <Card sectionKey="peer_insight" title="경쟁사 대비 강점·보완점" unit={c?.peers.length ? `(${c.peers.join(' · ')}와 비교)` : undefined}>
      {!c ? <p className={styles.muted}>{notice?.message ?? '경쟁사 비교 해석이 아직 없습니다.'}</p> : (
        <>
          <p className={styles.sub}>비교표에서 경쟁사보다 높은 점과 보완할 점을 봅니다. 뒤의 SWOT은 회사 안팎의 강점·약점·기회·위협을 자료 전반으로 정리합니다. 여기서 ‘개선 여지’는 시장 기회가 아니라 비교 지표에서 본 여지입니다.</p>
          {c.summary && <p className={styles.oneline}><AiBadge task="write_peers" /> {c.summary}</p>}
          <div className={styles.peergrid}>
            {PEER_GROUPS.map((g) => (
              <div key={g.key} className={`${styles.peerbox} ${g.cls}`}>
                <div className={styles.parttitle}>{g.title}</div>
                <p className={styles.sub}>{g.description}</p>
                {c[g.key].length === 0 ? <p className={styles.muted}>비교표에서 뚜렷하게 보이는 점이 없습니다.</p> : (
                  <ul className={styles.itemlist}>
                    {c[g.key].map((x) => (
                      <li key={x.text}>
                        {x.text} <span className={styles.sub}>근거: {x.basis.map((b) => labels[b] ?? b).join(', ')}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ))}
          </div>
          <p className={styles.footnote}>위 비교표의 숫자(코드 계산)를 보고 AI가 해석했습니다. 비교표에 없는 숫자가 든 문장은 버립니다. 투자 권유가 아닙니다.</p>
        </>
      )}
    </Card>
  )
}
