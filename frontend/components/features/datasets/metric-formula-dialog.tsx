'use client'

import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2, X } from 'lucide-react'
import { semanticService } from '@/lib/api/services'
import { useUIStore } from '@/store/use-ui-store'
import { formatNumber } from '@/lib/utils'
import { FormulaBuilder, type FormulaOperand } from '@/components/features/semantic/formula-builder'
import {
  astToGroup, formatGroup, groupToAst, isGroupComplete, ratioToGroup,
  type FormulaAggName, type FormulaGroup, type FormulaNode,
} from '@/lib/semantic/formula'
import type { ComputedMetric, SemanticMember } from '@/types'

interface MetricFormulaDialogProps {
  datasetId: string
  measures: SemanticMember[]
  metric?: ComputedMetric // present when editing an existing metric
  onClose: () => void
}

/** Numeric columns usable as formula operands (the raw catalog members). */
function columnOperands(measures: SemanticMember[]): FormulaOperand[] {
  const raw = measures.filter((m) => m.kind === 'measure' && m.agg == null)
  if (raw.length) return raw.map((m) => ({ name: m.name, label: m.title || m.name }))
  // Legacy fallback: derive base columns from the _sum variants.
  const seen = new Map<string, string>()
  for (const m of measures) {
    if (m.name.endsWith('_sum')) {
      seen.set(m.name.slice(0, -4), (m.title || m.name).replace(/ \(SUM\)$/i, ''))
    }
  }
  return [...seen.entries()].map(([name, label]) => ({ name, label }))
}

function initialGroup(metric: ComputedMetric | undefined, operands: FormulaOperand[]): FormulaGroup {
  if (metric) {
    const expr = metric.expression
    if (expr.type === 'formula' && expr.root) return astToGroup(expr.root as FormulaNode)
    if (expr.type === 'ratio') return ratioToGroup(expr)
    if (expr.type === 'aggregate') {
      return {
        terms: [{ kind: 'agg', agg: String(expr.agg || 'sum') as FormulaAggName, column: String(expr.column ?? '') }],
        ops: [],
      }
    }
  }
  // Fresh metric: start from the familiar SUM(a) ÷ SUM(b) shape.
  if (operands.length >= 2) {
    return {
      terms: [
        { kind: 'agg', agg: 'sum', column: operands[0].name },
        { kind: 'agg', agg: 'sum', column: operands[1].name },
      ],
      ops: ['/'],
    }
  }
  return { terms: [{ kind: 'agg', agg: 'sum', column: operands[0]?.name ?? '' }], ops: [] }
}

function useDebouncedValue<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), ms)
    return () => clearTimeout(t)
  }, [value, ms])
  return debounced
}

function apiErrorMessage(error: unknown, fallback: string): string {
  const detail = (error as { response?: { data?: { detail?: { message?: string } } } })
    ?.response?.data?.detail
  return detail?.message || fallback
}

export function MetricFormulaDialog({ datasetId, measures, metric, onClose }: MetricFormulaDialogProps) {
  const { addToast } = useUIStore()
  const qc = useQueryClient()
  const operands = useMemo(() => columnOperands(measures), [measures])
  const labelFor = (name: string) => operands.find((o) => o.name === name)?.label ?? name

  const [name, setName] = useState(metric?.name ?? '')
  const [displayName, setDisplayName] = useState(metric?.display_name ?? '')
  const [format, setFormat] = useState(metric?.format ?? 'number')
  const [group, setGroup] = useState<FormulaGroup>(() => initialGroup(metric, operands))

  const ast = useMemo<FormulaNode | null>(() => {
    if (!isGroupComplete(group)) return null
    try {
      return groupToAst(group)
    } catch {
      return null
    }
  }, [group])

  const astJson = ast ? JSON.stringify(ast) : null
  const debouncedAstJson = useDebouncedValue(astJson, 400)
  const previewQ = useQuery({
    queryKey: ['metric-preview', datasetId, debouncedAstJson],
    queryFn: () =>
      semanticService.previewMetric(datasetId, { type: 'formula', root: JSON.parse(debouncedAstJson as string) }),
    enabled: !!debouncedAstJson,
    staleTime: 60_000,
    retry: false,
  })

  const mutation = useMutation({
    mutationFn: () => {
      const payload = {
        display_name: displayName || name,
        format,
        expression: { type: 'formula', root: ast },
      }
      return metric
        ? semanticService.updateMetric(datasetId, metric.id, payload)
        : semanticService.createMetric(datasetId, {
            ...payload,
            name: name.trim().toLowerCase().replace(/[^a-z0-9_]/g, '_'),
          })
    },
    onSuccess: () => {
      addToast({ type: 'success', title: metric ? 'Metric updated' : 'Metric created' })
      qc.invalidateQueries({ queryKey: ['semantic-members', datasetId] })
      onClose()
    },
    onError: (error) =>
      addToast({
        type: 'error',
        title: metric ? 'Could not update metric' : 'Could not create metric',
        message: apiErrorMessage(error, 'Check the formula — the name may already exist.'),
      }),
  })

  const canSubmit = !!ast && (metric ? true : !!name.trim()) && !mutation.isPending

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div className="card w-full max-w-xl max-h-[85vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-semibold text-text-primary">
            {metric ? `Edit Metric — ${metric.display_name}` : 'New Computed Metric'}
          </h3>
          <button onClick={onClose} className="text-text-muted hover:text-text-primary"><X className="w-4 h-4" /></button>
        </div>
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-2">
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="name (e.g. profit_margin)"
              className="input-cyber disabled:opacity-50"
              disabled={!!metric}
            />
            <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} placeholder="Display name" className="input-cyber" />
          </div>

          <div className="bg-background/40 rounded p-3">
            <p className="text-[11px] uppercase tracking-wide text-text-muted mb-2">Formula</p>
            <FormulaBuilder mode="columns" operands={operands} value={group} onChange={setGroup} />
          </div>

          <div className="flex items-center gap-2 text-xs bg-background/40 rounded px-3 py-2 min-h-[2.25rem]">
            {ast ? (
              <>
                <span className="text-text-secondary truncate flex-1">{formatGroup(group, labelFor)}</span>
                {previewQ.isFetching ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin text-neon-blue shrink-0" />
                ) : previewQ.isError ? (
                  <span className="text-red-400 shrink-0">{apiErrorMessage(previewQ.error, 'Invalid formula')}</span>
                ) : previewQ.data ? (
                  <span className="text-neon-blue font-medium shrink-0">
                    = {previewQ.data.value == null ? '—' : formatNumber(Number(previewQ.data.value))}
                  </span>
                ) : null}
              </>
            ) : (
              <span className="text-text-muted">Complete the formula to see a live preview.</span>
            )}
          </div>

          <div className="grid grid-cols-2 gap-2">
            <select value={format} onChange={(e) => setFormat(e.target.value)} className="input-cyber py-1">
              <option value="number">Number</option>
              <option value="percent">Percent</option>
              <option value="currency">Currency</option>
            </select>
          </div>

          <button onClick={() => mutation.mutate()} disabled={!canSubmit} className="btn-primary w-full disabled:opacity-40">
            {mutation.isPending ? 'Saving…' : metric ? 'Update Metric' : 'Create Metric'}
          </button>
        </div>
      </div>
    </div>
  )
}
