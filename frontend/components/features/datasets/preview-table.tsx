'use client'

import { useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { ChevronLeft, ChevronRight, Filter, Loader2, Plus, Search, X } from 'lucide-react'
import { datasetService } from '@/lib/api/services'

const PAGE = 50

interface PreviewFilter {
  field: string
  operator: string
  value: string | number
}

const OPERATORS = [
  { key: 'contains', label: 'contains' },
  { key: '=', label: '=' },
  { key: '!=', label: '≠' },
  { key: '>', label: '>' },
  { key: '>=', label: '≥' },
  { key: '<', label: '<' },
  { key: '<=', label: '≤' },
]

/** Numeric comparisons get numeric values so DuckDB compares numbers, not text. */
function coerceValue(operator: string, value: string): string | number {
  if (['>', '>=', '<', '<='].includes(operator) && value.trim() !== '' && !Number.isNaN(Number(value))) {
    return Number(value)
  }
  return value
}

export function PreviewTable({ datasetId }: { datasetId: string }) {
  const [offset, setOffset] = useState(0)
  const [filters, setFilters] = useState<PreviewFilter[]>([])
  const [search, setSearch] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [draft, setDraft] = useState<{ field: string; operator: string; value: string }>({
    field: '', operator: 'contains', value: '',
  })

  const q = useQuery({
    queryKey: ['preview', datasetId, offset, JSON.stringify(filters), search],
    queryFn: () => datasetService.preview(datasetId, PAGE, offset, { filters, search }),
    placeholderData: keepPreviousData,
  })

  if (q.isLoading) return <div className="flex justify-center py-12"><Loader2 className="w-5 h-5 animate-spin text-neon-blue" /></div>
  if (q.isError || !q.data) return <p className="text-red-400 text-sm py-6">Failed to load preview.</p>

  const { rows, columns, total_rows, unfiltered_rows } = q.data
  const filtered = filters.length > 0 || !!search

  const applySearch = () => {
    setSearch(searchInput.trim())
    setOffset(0)
  }

  const addFilter = () => {
    const field = draft.field || columns[0]
    if (!field || draft.value.trim() === '') return
    setFilters([...filters, { field, operator: draft.operator, value: coerceValue(draft.operator, draft.value) }])
    setDraft({ ...draft, value: '' })
    setOffset(0)
  }

  const removeFilter = (i: number) => {
    setFilters(filters.filter((_, idx) => idx !== i))
    setOffset(0)
  }

  return (
    <div className="space-y-3">
      {/* Filter bar */}
      <div className="card py-2.5 px-3 space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-1.5 flex-1 min-w-[180px]">
            <Search className="w-3.5 h-3.5 text-text-muted shrink-0" />
            <input
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && applySearch()}
              onBlur={applySearch}
              placeholder="Search text columns…"
              className="input-cyber text-xs py-1 flex-1"
            />
          </div>
          <div className="flex items-center gap-1.5">
            <Filter className="w-3.5 h-3.5 text-text-muted shrink-0" />
            <select
              value={draft.field || columns[0] || ''}
              onChange={(e) => setDraft({ ...draft, field: e.target.value })}
              className="input-cyber text-xs py-1 max-w-[140px]"
              aria-label="Filter column"
            >
              {columns.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
            <select
              value={draft.operator}
              onChange={(e) => setDraft({ ...draft, operator: e.target.value })}
              className="input-cyber text-xs py-1 w-24"
              aria-label="Filter operator"
            >
              {OPERATORS.map((o) => <option key={o.key} value={o.key}>{o.label}</option>)}
            </select>
            <input
              value={draft.value}
              onChange={(e) => setDraft({ ...draft, value: e.target.value })}
              onKeyDown={(e) => e.key === 'Enter' && addFilter()}
              placeholder="value"
              className="input-cyber text-xs py-1 w-28"
              aria-label="Filter value"
            />
            <button onClick={addFilter} className="btn-ghost py-1 px-2 flex items-center gap-1 text-xs" title="Add filter">
              <Plus className="w-3.5 h-3.5" /> Filter
            </button>
          </div>
        </div>
        {(filters.length > 0 || search) && (
          <div className="flex flex-wrap items-center gap-1.5">
            {search && (
              <span className="flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full border border-neon-blue/40 text-neon-blue bg-neon-blue/10">
                search: “{search}”
                <button onClick={() => { setSearch(''); setSearchInput(''); setOffset(0) }} aria-label="Clear search"><X className="w-3 h-3" /></button>
              </span>
            )}
            {filters.map((f, i) => (
              <span key={`${f.field}-${i}`} className="flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full border border-neon-purple/40 text-neon-purple bg-neon-purple/10">
                {f.field} {OPERATORS.find((o) => o.key === f.operator)?.label ?? f.operator} {String(f.value)}
                <button onClick={() => removeFilter(i)} aria-label="Remove filter"><X className="w-3 h-3" /></button>
              </span>
            ))}
            <button
              onClick={() => { setFilters([]); setSearch(''); setSearchInput(''); setOffset(0) }}
              className="text-[11px] text-text-muted hover:text-text-primary underline"
            >
              clear all
            </button>
          </div>
        )}
      </div>

      <div className="overflow-x-auto card p-0 relative">
        {q.isFetching && <div className="absolute inset-0 bg-background/40 flex items-center justify-center z-10"><Loader2 className="w-5 h-5 animate-spin text-neon-blue" /></div>}
        <table className="w-full text-xs">
          <thead className="bg-background-secondary">
            <tr className="border-b border-border">
              {columns.map((c) => <th key={c} className="text-left py-2 px-3 text-text-secondary font-medium whitespace-nowrap">{c}</th>)}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr><td colSpan={columns.length} className="py-6 text-center text-text-muted">No rows match the current filters.</td></tr>
            ) : rows.map((row, i) => (
              <tr key={i} className="border-b border-border/40 hover:bg-background-hover">
                {columns.map((c) => <td key={c} className="py-1.5 px-3 text-text-primary whitespace-nowrap">{String(row[c] ?? '')}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex items-center justify-between text-xs text-text-muted">
        <span>
          {rows.length > 0 ? `${offset + 1}–${offset + rows.length}` : '0'}
          {total_rows != null ? ` of ${total_rows}` : ''}
          {filtered && unfiltered_rows != null ? ` (filtered from ${unfiltered_rows})` : ''}
        </span>
        <div className="flex gap-2">
          <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))} className="btn-ghost py-1 disabled:opacity-30"><ChevronLeft className="w-4 h-4" /></button>
          <button disabled={offset + rows.length >= (total_rows ?? 0)} onClick={() => setOffset(offset + PAGE)} className="btn-ghost py-1 disabled:opacity-30"><ChevronRight className="w-4 h-4" /></button>
        </div>
      </div>
    </div>
  )
}
