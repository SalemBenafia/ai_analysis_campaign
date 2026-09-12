'use client'

import { create } from 'zustand'
import type { FormulaNode } from '@/lib/semantic/formula'
import type { ChartType, SemanticFilter } from '@/types'

interface BuilderState {
  datasetId: string
  xField: string | null          // dimension or time member
  yFields: string[]              // measures
  colorField: string | null      // second dimension for breakout
  filters: SemanticFilter[]
  chartType: ChartType
  granularity: 'day' | 'week' | 'month'
  limit: number
  kpiExpression: FormulaNode | null // KPI custom calculation over yFields
  kpiLabel: string

  setDataset: (id: string) => void
  setX: (member: string | null) => void
  addY: (member: string) => void
  removeY: (member: string) => void
  setColor: (member: string | null) => void
  addFilter: (f: SemanticFilter) => void
  updateFilter: (i: number, f: SemanticFilter) => void
  removeFilter: (i: number) => void
  setChartType: (t: ChartType) => void
  setGranularity: (g: 'day' | 'week' | 'month') => void
  setKpiExpression: (expression: FormulaNode | null) => void
  setKpiLabel: (label: string) => void
  reset: () => void
  loadDefinition: (datasetId: string, def: Record<string, unknown>) => void
}

const initial = {
  datasetId: '',
  xField: null as string | null,
  yFields: [] as string[],
  colorField: null as string | null,
  filters: [] as SemanticFilter[],
  chartType: 'bar' as ChartType,
  granularity: 'day' as const,
  limit: 50,
  kpiExpression: null as FormulaNode | null,
  kpiLabel: '',
}

export const useBuilderStore = create<BuilderState>((set) => ({
  ...initial,

  setDataset: (id) => set({ ...initial, datasetId: id }),
  setX: (member) => set({ xField: member }),
  addY: (member) => set((s) => (s.yFields.includes(member) ? s : { yFields: [...s.yFields, member] })),
  removeY: (member) => set((s) => ({ yFields: s.yFields.filter((m) => m !== member) })),
  setColor: (member) => set({ colorField: member }),
  addFilter: (f) => set((s) => ({ filters: [...s.filters, f] })),
  updateFilter: (i, f) => set((s) => ({ filters: s.filters.map((x, idx) => (idx === i ? f : x)) })),
  removeFilter: (i) => set((s) => ({ filters: s.filters.filter((_, idx) => idx !== i) })),
  setChartType: (t) => set({ chartType: t }),
  setGranularity: (g) => set({ granularity: g }),
  setKpiExpression: (expression) => set({ kpiExpression: expression }),
  setKpiLabel: (label) => set({ kpiLabel: label }),
  reset: () => set(initial),

  loadDefinition: (datasetId, def) => {
    const kpi = (def.kpi as { expression?: { root?: FormulaNode }; label?: string }) || {}
    set({
      datasetId,
      xField: (def.time_dimension as string) || ((def.dimensions as string[]) || [])[0] || null,
      colorField: def.time_dimension
        ? ((def.dimensions as string[]) || [])[0] || null
        : ((def.dimensions as string[]) || [])[1] || null,
      yFields: (def.measures as string[]) || [],
      filters: (def.filters as SemanticFilter[]) || [],
      chartType: (def.visualization as ChartType) || 'bar',
      granularity: (def.granularity as 'day' | 'week' | 'month') || 'day',
      limit: (def.limit as number) || 50,
      kpiExpression: kpi.expression?.root ?? null,
      kpiLabel: kpi.label ?? '',
    })
  },
}))

/**
 * Compose the current builder state into a semantic query definition.
 * `timeMembers` is the set of member names that are time dimensions — used to
 * decide whether xField goes in time_dimension or dimensions[0].
 */
export function builderToDefinition(
  s: Pick<BuilderState, 'xField' | 'yFields' | 'colorField' | 'filters' | 'chartType' | 'granularity' | 'limit' | 'kpiExpression' | 'kpiLabel'>,
  timeMembers: Set<string>,
): Record<string, unknown> {
  const xIsTime = !!s.xField && timeMembers.has(s.xField)
  const dimensions: string[] = []
  let timeDimension: string | null = null

  if (s.xField) {
    if (xIsTime) timeDimension = s.xField
    else dimensions.push(s.xField)
  }
  if (s.colorField && s.colorField !== s.xField) dimensions.push(s.colorField)

  const definition: Record<string, unknown> = {
    version: 2,
    measures: s.yFields,
    dimensions,
    time_dimension: timeDimension,
    granularity: timeDimension ? s.granularity : null,
    filters: s.filters,
    order: {},
    limit: s.limit,
    visualization: s.chartType,
  }
  if (s.chartType === 'candlestick') definition.mode = 'ohlc'
  if (s.chartType === 'kpi' && s.kpiExpression) {
    definition.kpi = {
      expression: { type: 'formula', root: s.kpiExpression },
      ...(s.kpiLabel ? { label: s.kpiLabel } : {}),
    }
  }
  return definition
}
