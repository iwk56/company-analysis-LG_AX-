// Recharts 차트들. 값 표시는 format 함수를 거친다.
import {
  Bar, BarChart, CartesianGrid, ComposedChart, LabelList, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Scatter,
  ScatterChart, Tooltip, XAxis, YAxis, ZAxis,
} from 'recharts'
import styles from '../app.module.css'
import { paddedDomain } from '../format/domain'
import { snapMarks } from '../format/marks'
import { COLORS } from './palette'
import { formatChange, formatMultiple, formatPercent, formatWonTable } from '../format/number'
import type { Formatted } from '../format/number'

const EOK = 1e8

type Row = Record<string, number | string | null>

const eok = (v: unknown) => formatWonTable(Number(v) * EOK).text
const pct = (v: unknown) => formatPercent(Number(v) / 100).text
const times = (v: unknown) => formatMultiple(Number(v)).text

/** 5년 매출(막대, 억 원) + 영업이익률(선, %) */
export function TrendChart({ data }: { data: Row[] }) {
  return (
    <div className={styles.chartbox}>
      <ResponsiveContainer>
        <ComposedChart data={data} margin={{ top: 8, right: 8, left: 8, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="year" />
          <YAxis yAxisId="left" tickFormatter={eok} width={80} />
          <YAxis yAxisId="right" orientation="right" tickFormatter={pct} width={60} />
          <Tooltip formatter={(v, name) => (name === '영업이익률' ? pct(v) : eok(v))} />
          <Legend />
          <Bar yAxisId="left" dataKey="revenue" name="매출액(억 원)" fill={COLORS[0]} />
          <Line yAxisId="right" dataKey="margin" name="영업이익률" stroke={COLORS[1]} strokeWidth={2} connectNulls={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}

/** 비율 선 차트. unit이 '%'면 값은 이미 ×100, 'x'면 배수 */
export function LineGroupChart({ data, series, unit }: {
  data: Row[]
  series: { key: string; name: string }[]
  unit: '%' | 'x'
}) {
  const fmt = unit === '%' ? pct : times
  return (
    <div className={styles.chartbox}>
      <ResponsiveContainer>
        <LineChart data={data} margin={{ top: 8, right: 8, left: 8, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="year" />
          <YAxis tickFormatter={fmt} width={64} />
          <Tooltip formatter={(v) => fmt(v)} />
          <Legend />
          <ReferenceLine y={0} stroke="#999" />
          {series.map((s, i) => (
            <Line key={s.key} dataKey={s.key} name={s.name} stroke={COLORS[i % COLORS.length]} strokeWidth={2} connectNulls={false} />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

/** 영업·투자·재무 현금흐름 막대 (억 원) */
export function CashflowChart({ data }: { data: Row[] }) {
  return (
    <div className={styles.chartbox}>
      <ResponsiveContainer>
        <BarChart data={data} margin={{ top: 8, right: 8, left: 8, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="year" />
          <YAxis tickFormatter={eok} width={80} />
          <Tooltip formatter={(v) => eok(v)} />
          <Legend />
          <ReferenceLine y={0} stroke="#999" />
          <Bar dataKey="cfo" name="영업" fill={COLORS[0]} />
          <Bar dataKey="cfi" name="투자" fill={COLORS[1]} />
          <Bar dataKey="cff" name="재무" fill={COLORS[2]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

export interface ScatterPoint {
  corp_name: string
  x: number // 매출액증가율 (%)
  y: number // 영업이익률 (%)
}

/** 성장률(가로) × 영업이익률(세로) 점 그래프. 분석 기업만 다른 색, 점선은 비교 기업 평균 */
export function ComparisonScatter({ target, others, averageX, averageY }: {
  target: ScatterPoint[]
  others: ScatterPoint[]
  averageX: number | null // 퍼센트 단위
  averageY: number | null
}) {
  const growth = (v: unknown) => formatChange(Number(v) / 100).text
  const points = [...target, ...others]
  const xs = [...points.map((p) => p.x), ...(averageX === null ? [] : [averageX])]
  const ys = [...points.map((p) => p.y), ...(averageY === null ? [] : [averageY])]
  const xDomain = xs.length ? paddedDomain(xs, { low: 0.2, high: 0.3 }) : undefined
  const yDomain = ys.length ? paddedDomain(ys, { low: 0.2, high: 0.35 }) : undefined
  return (
    <>
      <div className={styles.chartbox} style={{ height: 340 }}>
        <ResponsiveContainer>
          <ScatterChart margin={{ top: 8, right: 40, left: 8, bottom: 8 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <Legend verticalAlign="top" height={32} />
            <XAxis type="number" dataKey="x" name="매출액증가율" tickFormatter={growth} domain={xDomain ?? ['auto', 'auto']}
              height={52} label={{ value: '매출액증가율', position: 'insideBottom', offset: 0 }} />
            <YAxis type="number" dataKey="y" name="영업이익률" tickFormatter={pct} domain={yDomain ?? ['auto', 'auto']}
              width={88} label={{ value: '영업이익률', angle: -90, position: 'insideLeft', offset: -2, style: { textAnchor: 'middle' } }} />
            <ZAxis range={[90, 90]} />
            <ReferenceLine x={0} stroke="#999" />
            <ReferenceLine y={0} stroke="#999" />
            {averageX !== null && <ReferenceLine x={averageX} stroke="#666" strokeDasharray="6 4" />}
            {averageY !== null && <ReferenceLine y={averageY} stroke="#666" strokeDasharray="6 4" />}
            <Tooltip cursor={{ strokeDasharray: '3 3' }}
              formatter={(v, name) => (name === '매출액증가율' ? growth(v) : pct(v))} />
            <Scatter name="분석 기업" data={target} fill={COLORS[1]} isAnimationActive={false}>
              <LabelList dataKey="corp_name" position="top" />
            </Scatter>
            <Scatter name="경쟁사" data={others} fill={COLORS[0]} isAnimationActive={false}>
              <LabelList dataKey="corp_name" position="top" />
            </Scatter>
          </ScatterChart>
        </ResponsiveContainer>
      </div>
      <p className={styles.footnote}>점선은 비교 기업 평균(분석 기업 포함)입니다.</p>
    </>
  )
}

/** 환율·기준금리 일별 추이 선 차트. 값 표시는 호출하는 쪽이 정한 format 함수를 거친다 */
export function SeriesChart({ points, name, format, color, step }: {
  points: { date: string; value: number }[]
  name: string
  format: (v: number) => Formatted
  color: string
  step?: boolean // 기준금리처럼 바뀐 날에만 값이 달라지는 경우 계단형
}) {
  const fmt = (v: unknown) => format(Number(v)).text
  const values = points.map((p) => p.value)
  const domain = values.length ? paddedDomain(values, { low: 0.1, high: 0.1 }) : undefined
  return (
    <div className={styles.chartbox}>
      <ResponsiveContainer>
        <LineChart data={points} margin={{ top: 8, right: 16, left: 8, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="date" minTickGap={48} tickFormatter={(d: string) => d.slice(0, 7)} />
          <YAxis tickFormatter={fmt} width={84} domain={domain ?? ['auto', 'auto']} />
          <Tooltip formatter={(v) => fmt(v)} labelFormatter={(d) => String(d)} />
          <Line dataKey="value" name={name} stroke={color} strokeWidth={2} dot={false} type={step ? 'stepAfter' : 'monotone'}
            isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

const OTHER_COLORS = [COLORS[0], COLORS[2], COLORS[3], '#64748b'] // 분석 기업은 COLORS[1]

/** 주가 흐름 비교: 기업마다 기준일 종가 = 100. lines의 key는 data 행의 열 이름 */
export function StockIndexChart({ data, lines, marks = [] }: {
  data: Row[]
  lines: { key: string; name: string; isTarget: boolean }[]
  marks?: { date: string; label: string }[] // 3페이지 공시 주제 날짜 (주제 번호)
}) {
  const snapped = snapMarks(data.map((r) => String(r.date)), marks)
  const values = data.flatMap((r) => lines.map((l) => r[l.key])).filter((v): v is number => typeof v === 'number')
  const domain = values.length ? paddedDomain([...values, 100], { low: 0.1, high: 0.1 }) : undefined
  let other = 0
  const colorOf = (l: { isTarget: boolean }) => (l.isTarget ? COLORS[1] : OTHER_COLORS[other++ % OTHER_COLORS.length])
  const colored = lines.map((l) => ({ ...l, color: colorOf(l) }))
  const idx = (v: unknown) => Number(v).toFixed(1)
  return (
    <div className={styles.chartbox}>
      <ResponsiveContainer>
        <LineChart data={data} margin={{ top: 8, right: 16, left: 8, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="date" minTickGap={48} tickFormatter={(d: string) => d.slice(0, 7)} />
          <YAxis tickFormatter={idx} width={56} domain={domain ?? ['auto', 'auto']} />
          <Tooltip formatter={(v) => idx(v)} labelFormatter={(d) => String(d)} />
          <Legend verticalAlign="top" height={28} />
          <ReferenceLine y={100} stroke="#94a3b8" strokeDasharray="4 4" />
          {snapped.map((m) => (
            <ReferenceLine key={m.date} x={m.date} stroke="#7c3aed" strokeDasharray="2 3" label={{ value: m.label, position: 'top', fill: '#7c3aed', fontSize: 12 }} />
          ))}
          {colored.map((l) => (
            <Line key={l.key} dataKey={l.key} name={l.isTarget ? `${l.name} (분석 기업)` : l.name} stroke={l.color}
              strokeWidth={l.isTarget ? 3 : 1.5} dot={false} connectNulls isAnimationActive={false} />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

/** 사업부문(품목)별 매출 비중 가로 막대. share는 퍼센트 단위(×100) */
export function SegmentChart({ data }: { data: { name: string; share: number }[] }) {
  const pctText = (v: unknown) => formatPercent(Number(v) / 100).text
  return (
    <div className={styles.chartbox} style={{ height: Math.max(120, data.length * 52 + 30) }}>
      <ResponsiveContainer>
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 56, left: 8, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" horizontal={false} />
          <XAxis type="number" domain={[0, 100]} tickFormatter={pctText} />
          <YAxis type="category" dataKey="name" width={110} />
          <Tooltip formatter={(v) => pctText(v)} />
          <Bar dataKey="share" name="매출 비중" fill={COLORS[0]} isAnimationActive={false}>
            <LabelList dataKey="share" position="right" formatter={(v: unknown) => pctText(v)} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
