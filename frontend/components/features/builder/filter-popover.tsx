'use client'

import { useState } from 'react'
import { Plus, X } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { FilterOperator, SemanticFilter, SemanticMember } from '@/types'

const OPERATORS: Array<{ value: FilterOperator; label: string }> = [
  { value: 'equals', label: '=' },
  { value: 'notEquals', label: '≠' },
  { value: 'gt', label: '>' },
  { value: 'gte', label: '≥' },
  { value: 'lt', label: '<' },
  { value: 'lte', label: '≤' },
  { value: 'contains', label: 'contains' },
]

interface FilterEditorProps {
  members: SemanticMember[]
  filters: SemanticFilter[]
  onAdd: (f: SemanticFilter) => void
  onRemove: (i: number) => void
  labelFor: (name: string) => string
}

export function FilterEditor({ members, filters, onAdd, onRemove, labelFor }: FilterEditorProps) {
  const [open, setOpen] = useState(false)
  const [member, setMember] = useState('')
  const [operator, setOperator] = useState<FilterOperator>('gt')
  const [value, setValue] = useState('')

  function add() {
    if (!member || value === '') return
    const num = Number(value)
    onAdd({ member, operator, values: [Number.isNaN(num) ? value : num] })
    setMember(''); setValue(''); setOpen(false)
  }

  return (
    <div>
      <p className="text-[11px] uppercase tracking-wide text-text-muted mb-1">Filters</p>
      <div className="space-y-1.5">
        {filters.map((f, i) => (
          <div key={i} className="flex items-center gap-1.5 text-xs bg-background-card border border-border rounded px-2 py-1">
            <span className="text-text-primary">{labelFor(f.member)}</span>
            <span className="text-neon-blue">{OPERATORS.find((o) => o.value === f.operator)?.label ?? f.operator}</span>
            <span className="text-text-secondary">{String(f.values[0] ?? '')}</span>
            <button onClick={() => onRemove(i)} className="ml-auto text-text-muted hover:text-text-primary">
              <X className="w-3 h-3" />
            </button>
          </div>
        ))}

        {open ? (
          <div className="space-y-1.5 border border-border rounded p-2 bg-background-card">
            <select value={member} onChange={(e) => setMember(e.target.value)} className="input-cyber text-xs py-1 w-full">
              <option value="">Field…</option>
              {members.map((m) => <option key={m.name} value={m.name}>{m.title}</option>)}
            </select>
            <div className="flex gap-1.5">
              <select value={operator} onChange={(e) => setOperator(e.target.value as FilterOperator)} className="input-cyber text-xs py-1 w-24">
                {OPERATORS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
              <input value={value} onChange={(e) => setValue(e.target.value)} placeholder="Value" className="input-cyber text-xs py-1 flex-1" />
            </div>
            <div className="flex gap-1.5">
              <button onClick={add} className="btn-primary text-xs py-1 flex-1">Add</button>
              <button onClick={() => setOpen(false)} className="btn-ghost text-xs py-1">Cancel</button>
            </div>
          </div>
        ) : (
          <button onClick={() => setOpen(true)} className={cn('flex items-center gap-1 text-xs text-text-muted hover:text-neon-blue')}>
            <Plus className="w-3 h-3" /> Add filter
          </button>
        )}
      </div>
    </div>
  )
}
