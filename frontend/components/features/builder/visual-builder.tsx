'use client'

import { useEffect, useMemo, useState } from 'react'
import { DndContext, DragEndEvent, PointerSensor, useSensor, useSensors } from '@dnd-kit/core'
import { useQuery } from '@tanstack/react-query'
import { Save, Loader2, AlertTriangle } from 'lucide-react'
import { semanticService } from '@/lib/api/services'
import { useSemanticMembers } from '@/hooks/use-semantic'
import { buildFromDefinition } from '@/lib/charts/build-option'
import { chartShape, validateChart, PICKER_TYPES } from '@/lib/charts/chart-rules'
import { ChartRender } from '@/components/features/charts/chart-render'
import { useBuilderStore, builderToDefinition } from './builder-state'
import { FieldsPanel } from './fields-panel'
import { Shelf } from './shelf'
import { FilterEditor } from './filter-popover'
import { ChartTypeSwitcher } from './chart-type-switcher'
import { KpiCalcPanel } from './kpi-calc-panel'
import { SaveInsightDialog } from './save-insight-dialog'
import type { ChartType, MemberCatalog, SemanticMember } from '@/types'

interface VisualBuilderProps {
  datasetId: string
  editInsightId?: string
}

function apiErrorMessage(error: unknown, fallback: string): string {
  const detail = (error as { response?: { data?: { detail?: { message?: string } } } })
    ?.response?.data?.detail
  return detail?.message || fallback
}

export function VisualBuilder({ datasetId, editInsightId }: VisualBuilderProps) {
  const s = useBuilderStore()
  const membersQ = useSemanticMembers(datasetId)
  const catalog = membersQ.data
  const [showSave, setShowSave] = useState(false)
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 4 } }))

  useEffect(() => {
    if (datasetId && s.datasetId !== datasetId && !editInsightId) s.setDataset(datasetId)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [datasetId])

  const memberIndex = useMemo(() => {
    const map = new Map<string, SemanticMember>()
    catalog?.dimensions.forEach((m) => map.set(m.name, m))
    catalog?.measures.forEach((m) => map.set(m.name, m))
    catalog?.computed_metrics.forEach((m) => map.set(m.name, { name: m.name, kind: 'computed', title: m.display_name, type: 'number', row_level: m.is_row_level }))
    return map
  }, [catalog])

  const timeMembers = useMemo(
    () => new Set((catalog?.dimensions ?? []).filter((m) => m.type === 'time').map((m) => m.name)),
    [catalog],
  )

  const labelFor = (name: string) => memberIndex.get(name)?.title ?? name

  const definition = useMemo(
    () => builderToDefinition(s, timeMembers),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [s.xField, s.yFields, s.colorField, s.filters, s.chartType, s.granularity, s.limit, s.kpiExpression, s.kpiLabel, timeMembers],
  )

  // Per-chart-type rules: disable impossible types, block invalid queries.
  const shape = useMemo(
    () => chartShape(s.yFields, s.xField, s.colorField, memberIndex, timeMembers),
    [s.yFields, s.xField, s.colorField, memberIndex, timeMembers],
  )
  const disabledReasons = useMemo(() => {
    const reasons: Partial<Record<ChartType, string>> = {}
    for (const type of PICKER_TYPES) {
      const violations = validateChart(type, shape)
      if (violations.length) reasons[type] = violations[0]
    }
    return reasons
  }, [shape])
  const violations = useMemo(() => validateChart(s.chartType, shape), [s.chartType, shape])

  const hasFields = s.yFields.length > 0
  const canQuery = hasFields && violations.length === 0
  const queryQ = useQuery({
    queryKey: ['builder-query', datasetId, JSON.stringify(definition)],
    queryFn: () => semanticService.query({ dataset_id: datasetId, ...(definition as object) }),
    enabled: !!datasetId && canQuery,
    staleTime: 5000,
  })

  function handleDrop(e: DragEndEvent) {
    const member = e.active.data.current?.member as SemanticMember | undefined
    const shelf = e.over?.id as string | undefined
    if (!member || !shelf) return
    if (shelf === 'shelf-x') s.setX(member.name)
    else if (shelf === 'shelf-y' && (member.kind === 'measure' || member.kind === 'computed')) s.addY(member.name)
    else if (shelf === 'shelf-color') s.setColor(member.name)
  }

  if (membersQ.isLoading) {
    return <div className="flex items-center justify-center h-64 text-text-muted"><Loader2 className="w-5 h-5 animate-spin mr-2" /> Loading fields…</div>
  }
  if (!catalog) return <div className="text-text-muted p-6">Select a ready dataset to start building.</div>

  const rows = queryQ.data?.rows ?? []
  const chartConfig = canQuery ? buildFromDefinition(rows, definition) : null

  return (
    <DndContext sensors={sensors} onDragEnd={handleDrop}>
      <div className="grid grid-cols-1 lg:grid-cols-[220px_1fr_260px] gap-4">
        {/* Fields */}
        <div className="card max-h-[70vh]">
          <FieldsPanel catalog={catalog} />
        </div>

        {/* Canvas */}
        <div className="space-y-3">
          <div className="flex items-start justify-between gap-2">
            <ChartTypeSwitcher value={s.chartType} onChange={s.setChartType} disabledReasons={disabledReasons} />
            <button
              onClick={() => setShowSave(true)}
              disabled={!canQuery}
              className="btn-primary flex items-center gap-2 disabled:opacity-40 whitespace-nowrap"
            >
              <Save className="w-4 h-4" /> Save
            </button>
          </div>

          <div className="card min-h-[360px] flex items-center justify-center">
            {!hasFields ? (
              <p className="text-text-muted text-sm">Drag a measure into the Y shelf to build a chart.</p>
            ) : violations.length > 0 ? (
              <div className="space-y-2 text-sm max-w-md">
                {violations.map((message) => (
                  <p key={message} className="flex items-start gap-2 text-amber-400">
                    <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" /> {message}
                  </p>
                ))}
              </div>
            ) : queryQ.isFetching ? (
              <Loader2 className="w-6 h-6 animate-spin text-neon-blue" />
            ) : queryQ.isError ? (
              <p className="text-red-400 text-sm">{apiErrorMessage(queryQ.error, 'Query failed. Check field combinations.')}</p>
            ) : chartConfig ? (
              <ChartRender config={chartConfig} height={340} />
            ) : null}
          </div>
          {queryQ.data?.meta && canQuery && (
            <p className="text-[11px] text-text-muted text-right">
              {rows.length} rows · {queryQ.data.meta.engine} · {queryQ.data.meta.took_ms}ms
            </p>
          )}
        </div>

        {/* Config */}
        <div className="card space-y-4 max-h-[70vh] overflow-y-auto">
          <Shelf id="shelf-x" label="X / Group by" items={s.xField ? [s.xField] : []} labelFor={labelFor} onRemove={() => s.setX(null)} hint="Drop a dimension" />
          <Shelf id="shelf-y" label="Y / Measures" items={s.yFields} labelFor={labelFor} onRemove={s.removeY} hint="Drop measures" />
          <Shelf id="shelf-color" label="Break down by" items={s.colorField ? [s.colorField] : []} labelFor={labelFor} onRemove={() => s.setColor(null)} hint="Optional dimension" accent="purple" />
          {s.xField && timeMembers.has(s.xField) && (
            <div>
              <p className="text-[11px] uppercase tracking-wide text-text-muted mb-1">Granularity</p>
              <select value={s.granularity} onChange={(e) => s.setGranularity(e.target.value as 'day' | 'week' | 'month')} className="input-cyber text-xs py-1 w-full">
                <option value="day">Day</option>
                <option value="week">Week</option>
                <option value="month">Month</option>
              </select>
            </div>
          )}
          {s.chartType === 'kpi' && (
            <KpiCalcPanel operands={s.yFields.map((name) => ({ name, label: labelFor(name) }))} />
          )}
          <FilterEditor
            members={[...catalog.dimensions, ...catalog.measures]}
            filters={s.filters}
            onAdd={s.addFilter}
            onRemove={s.removeFilter}
            labelFor={labelFor}
          />
        </div>
      </div>

      {showSave && (
        <SaveInsightDialog
          datasetId={datasetId}
          definition={definition}
          existingId={editInsightId}
          onClose={() => setShowSave(false)}
        />
      )}
    </DndContext>
  )
}
