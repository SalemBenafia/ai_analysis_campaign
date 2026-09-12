'use client'

import { Parentheses, Plus, Trash2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import {
  AGG_LABEL, FORMULA_AGGS, OP_SYMBOL,
  type FormulaAggName, type FormulaGroup, type FormulaOp, type FormulaTerm,
} from '@/lib/semantic/formula'

export interface FormulaOperand {
  name: string
  label: string
}

interface FormulaBuilderProps {
  /** 'columns' composes AGG(column) terms; 'measures' composes references to selected measures (KPI). */
  mode: 'columns' | 'measures'
  operands: FormulaOperand[]
  value: FormulaGroup
  onChange: (group: FormulaGroup) => void
  depth?: number
}

const OPS: FormulaOp[] = ['+', '-', '*', '/']
const MAX_GROUP_DEPTH = 3

export function emptyGroup(): FormulaGroup {
  return { terms: [], ops: [] }
}

function newFieldTerm(mode: 'columns' | 'measures', operands: FormulaOperand[]): FormulaTerm {
  if (mode === 'measures') return { kind: 'ref', measure: operands[0]?.name ?? '' }
  return { kind: 'agg', agg: 'sum', column: operands[0]?.name ?? '' }
}

export function FormulaBuilder({ mode, operands, value, onChange, depth = 0 }: FormulaBuilderProps) {
  const setTerm = (i: number, term: FormulaTerm) =>
    onChange({ ...value, terms: value.terms.map((t, idx) => (idx === i ? term : t)) })

  const setOp = (i: number, op: FormulaOp) =>
    onChange({ ...value, ops: value.ops.map((o, idx) => (idx === i ? op : o)) })

  const addTerm = (term: FormulaTerm) =>
    onChange(
      value.terms.length === 0
        ? { terms: [term], ops: [] }
        : { terms: [...value.terms, term], ops: [...value.ops, mode === 'columns' ? '/' : '-'] },
    )

  const removeTerm = (i: number) => {
    const terms = value.terms.filter((_, idx) => idx !== i)
    const ops = [...value.ops]
    ops.splice(Math.max(0, i - 1), 1)
    onChange({ terms, ops })
  }

  return (
    <div className={cn('space-y-1.5', depth > 0 && 'border-l-2 border-neon-purple/30 pl-3')}>
      {value.terms.map((term, i) => (
        <div key={i} className="flex items-start gap-1.5">
          {i > 0 ? (
            <select
              value={value.ops[i - 1]}
              onChange={(e) => setOp(i - 1, e.target.value as FormulaOp)}
              className="input-cyber py-1 px-1.5 text-sm w-12 shrink-0"
              aria-label="Operator"
            >
              {OPS.map((op) => <option key={op} value={op}>{OP_SYMBOL[op]}</option>)}
            </select>
          ) : (
            <span className="w-12 shrink-0" />
          )}

          <div className="flex-1 min-w-0">
            {term.kind === 'agg' && (
              <div className="flex items-center gap-1.5">
                <select
                  value={term.agg}
                  onChange={(e) => setTerm(i, { ...term, agg: e.target.value as FormulaAggName })}
                  className="input-cyber py-1 text-xs w-36 shrink-0"
                  aria-label="Aggregation"
                >
                  {FORMULA_AGGS.map((a) => <option key={a} value={a}>{AGG_LABEL[a]}</option>)}
                </select>
                <select
                  value={term.column}
                  onChange={(e) => setTerm(i, { ...term, column: e.target.value })}
                  className="input-cyber py-1 text-xs flex-1 min-w-0"
                  aria-label="Column"
                >
                  {!term.column && <option value="">column…</option>}
                  {operands.map((o) => <option key={o.name} value={o.name}>{o.label}</option>)}
                </select>
              </div>
            )}
            {term.kind === 'ref' && (
              <select
                value={term.measure}
                onChange={(e) => setTerm(i, { ...term, measure: e.target.value })}
                className="input-cyber py-1 text-xs w-full"
                aria-label="Measure"
              >
                {!term.measure && <option value="">measure…</option>}
                {operands.map((o) => <option key={o.name} value={o.name}>{o.label}</option>)}
              </select>
            )}
            {term.kind === 'literal' && (
              <input
                type="number"
                step="any"
                value={Number.isFinite(term.value) ? term.value : ''}
                onChange={(e) => setTerm(i, { ...term, value: e.target.valueAsNumber })}
                className="input-cyber py-1 text-xs w-full"
                placeholder="number"
                aria-label="Number"
              />
            )}
            {term.kind === 'group' && (
              <FormulaBuilder
                mode={mode}
                operands={operands}
                value={term.group}
                onChange={(group) => setTerm(i, { kind: 'group', group })}
                depth={depth + 1}
              />
            )}
          </div>

          <button
            onClick={() => removeTerm(i)}
            className="text-text-muted hover:text-red-400 mt-1.5 shrink-0"
            title="Remove term"
            type="button"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      ))}

      <div className="flex items-center gap-2 pl-[3.375rem]">
        <button onClick={() => addTerm(newFieldTerm(mode, operands))} className="btn-ghost flex items-center gap-1 text-[11px] py-0.5" type="button">
          <Plus className="w-3 h-3" /> {mode === 'columns' ? 'Field' : 'Measure'}
        </button>
        <button onClick={() => addTerm({ kind: 'literal', value: 100 })} className="btn-ghost flex items-center gap-1 text-[11px] py-0.5" type="button">
          <Plus className="w-3 h-3" /> Number
        </button>
        {depth < MAX_GROUP_DEPTH && (
          <button
            onClick={() => addTerm({ kind: 'group', group: { terms: [newFieldTerm(mode, operands)], ops: [] } })}
            className="btn-ghost flex items-center gap-1 text-[11px] py-0.5"
            title="Parenthesized group"
            type="button"
          >
            <Parentheses className="w-3 h-3" /> Group
          </button>
        )}
      </div>
    </div>
  )
}
