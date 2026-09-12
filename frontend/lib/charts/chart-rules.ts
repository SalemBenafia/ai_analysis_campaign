/**
 * Per-chart-type shape rules: how many aggregated/raw measures and dimensions
 * each visualization accepts, and whether a time dimension is required.
 * Drives the builder (disabled chart types, violation messages, "N of 7
 * possible" counter); the backend enforces the same matrix on save.
 *
 * KEEP IN SYNC with backend app/modules/visualization/chart_rules.py
 */
import type { ChartType, SemanticMember } from '@/types'

export interface ChartShape {
  agg: number // aggregated measures (incl. computed metrics)
  raw: number // raw column measures (no aggregation)
  dims: number // non-time dimensions (X when not time + breakdown)
  hasTime: boolean
  hasGranularity: boolean
}

interface Rule {
  agg: [number, number | null] // [min, max] — max null means unbounded
  raw: [number, number | null]
  dims: [number, number]
  time: 'allowed' | 'required' | 'forbidden'
  granularity?: 'required'
  minMeasures?: number // at least N measures of any kind
  noMix?: boolean // can't combine raw and aggregated measures
}

export const CHART_RULES: Partial<Record<ChartType, Rule>> = {
  bar: { agg: [1, null], raw: [0, 0], dims: [0, 2], time: 'allowed' },
  // Line accepts raw measures for real-time raw tracking, or aggregated
  // measures — but not both mixed.
  line: { agg: [0, null], raw: [0, null], dims: [0, 2], time: 'allowed', minMeasures: 1, noMix: true },
  area: { agg: [1, null], raw: [0, 0], dims: [0, 2], time: 'allowed' },
  pie: { agg: [1, 1], raw: [0, 0], dims: [1, 1], time: 'forbidden' },
  scatter: { agg: [2, 2], raw: [0, 0], dims: [0, 1], time: 'forbidden' },
  kpi: { agg: [1, null], raw: [0, 0], dims: [0, 0], time: 'forbidden' },
  candlestick: { agg: [0, 0], raw: [1, 1], dims: [0, 0], time: 'required', granularity: 'required' },
  // 'table' is intentionally absent: renderer-only legacy type, any shape.
}

/** Chart types offered by the builder picker. */
export const PICKER_TYPES: ChartType[] = ['bar', 'line', 'area', 'pie', 'scatter', 'candlestick', 'kpi']

/** Requirement summary per type (tooltips). */
export const RULE_HINTS: Partial<Record<ChartType, string>> = {
  bar: '1+ measures · up to 2 dimensions',
  line: '1+ measures · raw allowed for real-time tracking · X is time or a dimension',
  area: '1+ measures · X is time or a dimension',
  pie: 'exactly 1 measure · exactly 1 dimension · no time',
  scatter: 'exactly 2 measures (X and Y) · optional color',
  kpi: '1+ measures · no dimensions',
  candlestick: '1 raw measure (e.g. "Spend") · time on X · granularity',
}

function isRawMeasure(member: SemanticMember | undefined): boolean {
  if (!member) return false
  // Raw column measures (no agg) and row-level formula metrics both plot raw
  // row-level values.
  return member.row_level === true || (member.kind === 'measure' && member.agg == null)
}

/** Reduce the builder selection to the shape the rules check. */
export function chartShape(
  yFields: string[],
  xField: string | null,
  colorField: string | null,
  memberIndex: Map<string, SemanticMember>,
  timeMembers: Set<string>,
): ChartShape {
  let agg = 0
  let raw = 0
  for (const y of yFields) {
    if (isRawMeasure(memberIndex.get(y))) raw++
    else agg++
  }
  const hasTime = !!xField && timeMembers.has(xField)
  let dims = 0
  if (xField && !hasTime) dims++
  if (colorField && colorField !== xField) dims++
  return { agg, raw, dims, hasTime, hasGranularity: true } // builder always has a granularity selected
}

function checkRange(
  count: number,
  [lo, hi]: [number, number | null],
  label: string,
  chart: string,
): string | null {
  if (count < lo) {
    const need = hi == null || hi > lo ? `at least ${lo}` : `exactly ${lo}`
    return `${chart} needs ${need} ${label} — add ${lo - count} more`
  }
  if (hi != null && count > hi) {
    const allowed = hi > 0 ? `at most ${hi}` : 'no'
    return `${chart} allows ${allowed} ${label} — remove ${count - hi}`
  }
  return null
}

/** Actionable violation messages for a chart type ([] when the shape fits). */
export function validateChart(type: ChartType, shape: ChartShape): string[] {
  const rules = CHART_RULES[type]
  if (!rules) return [] // table / unknown: renderer-only
  const chart = type.charAt(0).toUpperCase() + type.slice(1)
  const messages: string[] = []

  const aggMsg = checkRange(shape.agg, rules.agg, 'aggregated measure(s)', chart)
  if (aggMsg) messages.push(aggMsg)

  const rawMsg = checkRange(shape.raw, rules.raw, 'raw measure(s)', chart)
  if (rawMsg) {
    messages.push(
      type === 'candlestick' && shape.raw < 1
        ? 'Candlestick needs exactly 1 raw measure — drop the plain "Spend"-style field, not "Spend (SUM)"'
        : rawMsg,
    )
  }

  const dimMsg = checkRange(shape.dims, rules.dims, 'dimension(s)', chart)
  if (dimMsg) messages.push(dimMsg)

  if (rules.minMeasures && shape.agg + shape.raw < rules.minMeasures) {
    messages.push(`${chart} needs at least ${rules.minMeasures} measure — add one`)
  }
  if (rules.noMix && shape.agg > 0 && shape.raw > 0) {
    messages.push(`${chart} can't mix raw and aggregated measures — use one kind`)
  }

  if (rules.time === 'required' && !shape.hasTime) {
    messages.push(`${chart} needs a time dimension on X`)
  } else if (rules.time === 'forbidden' && shape.hasTime) {
    messages.push(`${chart} can't use a time dimension — remove it from X`)
  }

  if (rules.granularity === 'required' && shape.hasTime && !shape.hasGranularity) {
    messages.push(`${chart} needs a granularity (day, week or month)`)
  }

  return messages
}

/** Which picker types are valid for the current shape. */
export function possibleTypes(shape: ChartShape): ChartType[] {
  return PICKER_TYPES.filter((t) => validateChart(t, shape).length === 0)
}
