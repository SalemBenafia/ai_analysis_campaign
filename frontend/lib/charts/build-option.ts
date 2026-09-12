import { evaluateFormula, type FormulaNode } from '@/lib/semantic/formula'
import type { ChartType } from '@/types'

const ACCENT = '#00d4ff'
const PALETTE = ['#00d4ff', '#a855f7', '#22c55e', '#f59e0b', '#ef4444', '#3b82f6', '#ec4899', '#14b8a6']
const AXIS = { color: '#94a3b8', fontSize: 10 }

type Row = Record<string, unknown>

interface KpiSpec {
  expression?: Record<string, unknown>
  label?: string
}

interface BuildOpts {
  rows: Row[]
  chartType: ChartType
  xField?: string | null
  yFields: string[]
  title?: string
  colorField?: string | null
  kpi?: KpiSpec | null
}

function base(title: string): Record<string, unknown> {
  return {
    backgroundColor: 'transparent',
    title: title ? { text: title, textStyle: { color: '#e2e8f0', fontSize: 13 } } : {},
    tooltip: { trigger: 'axis' },
    legend: { textStyle: { color: '#94a3b8' }, top: 'bottom' },
    grid: { left: '3%', right: '4%', bottom: '14%', top: '16%', containLabel: true },
    color: PALETTE,
  }
}

function series(chartType: ChartType, name: string, data: number[]): Record<string, unknown> {
  const isLine = chartType === 'line' || chartType === 'area'
  const s: Record<string, unknown> = { type: isLine ? 'line' : 'bar', name, data }
  if (chartType === 'area') { s.areaStyle = { opacity: 0.25 }; s.smooth = true }
  else if (chartType === 'line') s.smooth = true
  return s
}

/** Build an ECharts option from rows + a chart spec. Mirrors the backend builder. */
export function buildOption(opts: BuildOpts): Record<string, unknown> {
  const { rows, chartType, xField, yFields, title = '', colorField, kpi } = opts
  const ys = yFields.filter(Boolean)
  if (!rows.length || !ys.length) return { ...base(title), series: [] }

  if (chartType === 'kpi') {
    // Reduce every measure to a total; a custom calculation (ref/literal
    // formula over those totals) wins over the default first-measure sum.
    const totals: Record<string, number> = {}
    for (const y of ys) totals[y] = rows.reduce((acc, r) => acc + Number(r[y] ?? 0), 0)
    let value: number | null = totals[ys[0]] ?? null
    const root = (kpi?.expression as { root?: FormulaNode } | undefined)?.root
    if (root) value = evaluateFormula(root, totals)
    return { type: 'kpi', title, metric: kpi?.label || ys[0], value }
  }

  if (chartType === 'table') {
    const cols = (xField ? [xField] : []).concat(ys)
    return {
      type: 'table',
      title,
      columns: cols,
      rows: rows.map((r) => cols.map((c) => r[c])),
    }
  }

  const xVals = xField ? rows.map((r) => String(r[xField] ?? '')) : rows.map((_, i) => String(i))
  const opt = base(title)

  if (chartType === 'candlestick') {
    // Rows come from the OHLC query: fixed open/high/low/close keys.
    // ECharts candlestick data item order is [open, close, lowest, highest].
    return {
      ...opt,
      tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
      xAxis: { type: 'category', data: xVals, axisLabel: AXIS },
      yAxis: { type: 'value', scale: true, axisLabel: AXIS },
      series: [{
        type: 'candlestick',
        name: ys[0],
        data: rows.map((r) => [Number(r.open ?? 0), Number(r.close ?? 0), Number(r.low ?? 0), Number(r.high ?? 0)]),
        itemStyle: { color: '#22c55e', color0: '#ef4444', borderColor: '#22c55e', borderColor0: '#ef4444' },
      }],
    }
  }

  if (chartType === 'pie') {
    const y = ys[0]
    return {
      ...opt,
      tooltip: { trigger: 'item' },
      series: [{
        type: 'pie',
        radius: ['40%', '70%'],
        data: xVals.map((name, i) => ({ name, value: Number(rows[i][y] ?? 0) })),
        label: { color: '#94a3b8' },
      }],
    }
  }

  if (chartType === 'scatter') {
    const xm = ys[0]
    const ym = ys[1] ?? ys[0]
    return {
      ...opt,
      tooltip: { trigger: 'item' },
      xAxis: { type: 'value', name: xm, axisLabel: AXIS },
      yAxis: { type: 'value', name: ym, axisLabel: AXIS },
      series: [{ type: 'scatter', data: rows.map((r) => [Number(r[xm] ?? 0), Number(r[ym] ?? 0)]), itemStyle: { color: ACCENT } }],
    }
  }

  // bar / line / area
  opt.xAxis = { type: 'category', data: xVals, axisLabel: AXIS }
  opt.yAxis = { type: 'value', axisLabel: AXIS }

  if (colorField && ys.length === 1 && xField) {
    const y = ys[0]
    const cats: string[] = []
    const groups: Record<string, Record<string, number>> = {}
    for (const r of rows) {
      const cat = String(r[xField] ?? '')
      if (!cats.includes(cat)) cats.push(cat)
      const grp = String(r[colorField] ?? '')
      groups[grp] = groups[grp] || {}
      groups[grp][cat] = Number(r[y] ?? 0)
    }
    opt.xAxis = { type: 'category', data: cats, axisLabel: AXIS }
    opt.series = Object.entries(groups).map(([grp, vals]) => series(chartType, grp, cats.map((c) => vals[c] ?? 0)))
  } else {
    opt.series = ys.map((y) => series(chartType, y, rows.map((r) => Number(r[y] ?? 0))))
  }
  return opt
}

/** Build an option from a v2 insight/semantic definition + rows. */
export function buildFromDefinition(rows: Row[], definition: Record<string, unknown>): Record<string, unknown> {
  const dims = (definition.dimensions as string[]) || []
  const timeDim = definition.time_dimension as string | undefined
  const measures = (definition.measures as string[]) || []
  const viz = (definition.visualization as ChartType) || 'bar'

  const xField = timeDim || dims[0] || null
  let colorField: string | null = null
  if (!timeDim && dims.length > 1) colorField = dims[1]
  else if (timeDim && dims.length) colorField = dims[0]

  return buildOption({
    rows, chartType: viz, xField, yFields: measures,
    title: (definition.title as string) || '', colorField,
    kpi: (definition.kpi as KpiSpec) || null,
  })
}
