// Recharts 차트들. 값 표시는 format 함수를 거친다.
import {
  Bar, BarChart, CartesianGrid, ComposedChart, LabelList, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Scatter,
  ScatterChart, Tooltip, XAxis, YAxis, ZAxis,
} from 'recharts'
import styles from '../app.module.css'
import { formatChange, formatMultiple, formatPercent, formatWonTable } from '../format/number'

const COLORS = ['#2456a6', '#d97706', '#1b873f', '#8e44ad']
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

/** 성장률(가로) × 영업이익률(세로) 점 그래프. 분석 기업만 다른 색 */
export function ComparisonScatter({ target, others }: { target: ScatterPoint[]; others: ScatterPoint[] }) {
  const growth = (v: unknown) => formatChange(Number(v) / 100).text
  return (
    <div className={styles.chartbox}>
      <ResponsiveContainer>
        <ScatterChart margin={{ top: 16, right: 32, left: 8, bottom: 16 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis type="number" dataKey="x" name="매출액증가율" tickFormatter={growth} domain={['auto', 'auto']}
            label={{ value: '매출액증가율', position: 'insideBottom', offset: -8 }} />
          <YAxis type="number" dataKey="y" name="영업이익률" tickFormatter={pct} width={64} domain={['auto', 'auto']} />
          <ZAxis range={[90, 90]} />
          <ReferenceLine x={0} stroke="#999" />
          <ReferenceLine y={0} stroke="#999" />
          <Tooltip cursor={{ strokeDasharray: '3 3' }}
            formatter={(v, name) => (name === '매출액증가율' ? growth(v) : pct(v))} />
          <Legend />
          <Scatter name="분석 기업" data={target} fill={COLORS[1]}>
            <LabelList dataKey="corp_name" position="top" />
          </Scatter>
          <Scatter name="경쟁사" data={others} fill={COLORS[0]}>
            <LabelList dataKey="corp_name" position="top" />
          </Scatter>
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  )
}
