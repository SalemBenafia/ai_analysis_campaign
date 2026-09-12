'use client'

import { BarChart2, CandlestickChart, LineChart, PieChart, TrendingUp, ScatterChart, Table, Hash } from 'lucide-react'
import { cn } from '@/lib/utils'
import { PICKER_TYPES, RULE_HINTS } from '@/lib/charts/chart-rules'
import type { ChartType } from '@/types'

const ICONS: Partial<Record<ChartType, typeof BarChart2>> = {
  bar: BarChart2,
  line: LineChart,
  area: TrendingUp,
  pie: PieChart,
  scatter: ScatterChart,
  candlestick: CandlestickChart,
  kpi: Hash,
}

const LABELS: Partial<Record<ChartType, string>> = {
  bar: 'Bar',
  line: 'Line',
  area: 'Area',
  pie: 'Pie',
  scatter: 'Scatter',
  candlestick: 'Candle',
  kpi: 'KPI',
}

interface ChartTypeSwitcherProps {
  value: ChartType
  onChange: (t: ChartType) => void
  /** First rule violation per chart type; a type with an entry renders disabled. */
  disabledReasons?: Partial<Record<ChartType, string>>
}

export function ChartTypeSwitcher({ value, onChange, disabledReasons = {} }: ChartTypeSwitcherProps) {
  const possible = PICKER_TYPES.filter((t) => !disabledReasons[t]).length

  return (
    <div className="space-y-1">
      <div className="flex flex-wrap gap-1.5 items-center">
        {PICKER_TYPES.map((type) => {
          const Icon = ICONS[type] ?? BarChart2
          const reason = disabledReasons[type]
          return (
            <button
              key={type}
              onClick={() => !reason && onChange(type)}
              disabled={!!reason}
              className={cn(
                'flex items-center gap-1.5 px-2.5 py-1.5 rounded-md border text-xs transition-colors',
                value === type
                  ? 'border-neon-blue/60 text-neon-blue bg-neon-blue/10'
                  : reason
                    ? 'border-border/50 text-text-muted opacity-50 cursor-not-allowed'
                    : 'border-border text-text-secondary hover:border-neon-blue/30',
              )}
              title={reason ? `${reason} · Requires: ${RULE_HINTS[type] ?? ''}` : RULE_HINTS[type] ?? LABELS[type]}
            >
              <Icon className="w-3.5 h-3.5" /> {LABELS[type]}
            </button>
          )
        })}
        {value === 'table' && (
          // Legacy insight being edited: table left the picker but must stay selectable.
          <button
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md border text-xs border-neon-blue/60 text-neon-blue bg-neon-blue/10"
            title="Table is a legacy chart type — pick another type to switch away"
          >
            <Table className="w-3.5 h-3.5" /> Table (legacy)
          </button>
        )}
      </div>
      <p className="text-[10px] text-text-muted">
        {possible} of {PICKER_TYPES.length} chart types possible with the current fields
      </p>
    </div>
  )
}
