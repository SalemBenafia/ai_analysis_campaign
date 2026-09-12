'use client'

import { useState } from 'react'
import { FormulaBuilder, type FormulaOperand } from '@/components/features/semantic/formula-builder'
import {
  astToGroup, formatGroup, groupToAst, isGroupComplete,
  type FormulaGroup,
} from '@/lib/semantic/formula'
import { useBuilderStore } from './builder-state'

function defaultGroup(operands: FormulaOperand[]): FormulaGroup {
  if (operands.length >= 2) {
    return {
      terms: [
        { kind: 'ref', measure: operands[0].name },
        { kind: 'ref', measure: operands[1].name },
      ],
      ops: ['-'],
    }
  }
  return { terms: [{ kind: 'ref', measure: operands[0]?.name ?? '' }], ops: [] }
}

/**
 * KPI custom calculation: compose a formula over the selected measures'
 * totals, e.g. (Revenue − Spend) ÷ Spend × 100. Without it the KPI shows
 * the first measure's total, as before.
 */
export function KpiCalcPanel({ operands }: { operands: FormulaOperand[] }) {
  const s = useBuilderStore()
  const [enabled, setEnabled] = useState(s.kpiExpression != null)
  const [group, setGroup] = useState<FormulaGroup>(() =>
    s.kpiExpression ? astToGroup(s.kpiExpression) : defaultGroup(operands),
  )
  const labelFor = (name: string) => operands.find((o) => o.name === name)?.label ?? name

  const pushToStore = (g: FormulaGroup) => {
    if (isGroupComplete(g)) {
      try {
        s.setKpiExpression(groupToAst(g))
        return
      } catch {
        // fall through
      }
    }
    s.setKpiExpression(null)
  }

  const toggle = (on: boolean) => {
    setEnabled(on)
    if (on) {
      const g = s.kpiExpression ? astToGroup(s.kpiExpression) : defaultGroup(operands)
      setGroup(g)
      pushToStore(g)
    } else {
      s.setKpiExpression(null)
    }
  }

  return (
    <div>
      <label className="flex items-center gap-2 text-[11px] uppercase tracking-wide text-text-muted mb-1 cursor-pointer">
        <input type="checkbox" checked={enabled} onChange={(e) => toggle(e.target.checked)} />
        KPI custom calculation
      </label>
      {enabled ? (
        operands.length === 0 ? (
          <p className="text-xs text-text-muted">Add measures to the Y shelf first.</p>
        ) : (
          <div className="space-y-2">
            <FormulaBuilder
              mode="measures"
              operands={operands}
              value={group}
              onChange={(g) => {
                setGroup(g)
                pushToStore(g)
              }}
            />
            <input
              value={s.kpiLabel}
              onChange={(e) => s.setKpiLabel(e.target.value)}
              placeholder="KPI label (e.g. Margin %)"
              className="input-cyber text-xs py-1 w-full"
            />
            <p className="text-[11px] text-text-secondary truncate">
              {isGroupComplete(group) ? `= ${formatGroup(group, labelFor)}` : 'Complete the calculation…'}
            </p>
          </div>
        )
      ) : (
        <p className="text-[11px] text-text-muted">Off — the KPI shows the first measure&apos;s total.</p>
      )}
    </div>
  )
}
