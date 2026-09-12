'use client'

import { EChartWrapper } from './echart-wrapper'
import { formatNumber } from '@/lib/utils'

interface ChartRenderProps {
  config: Record<string, unknown>
  height?: number | string
}

/**
 * Renders a chart config from the shared builder. Most configs are ECharts
 * options; kpi and table configs (which carry a `type` field) render as
 * bespoke tiles instead of feeding ECharts.
 */
export function ChartRender({ config, height = 300 }: ChartRenderProps) {
  const kind = config?.type as string | undefined

  if (kind === 'kpi') {
    const value = Number(config.value ?? 0)
    return (
      <div className="flex flex-col items-center justify-center gap-1" style={{ height }}>
        <span className="text-xs text-text-muted uppercase tracking-wide">{String(config.metric ?? '')}</span>
        <span className="text-4xl font-bold text-neon-blue">{formatNumber(value)}</span>
        {config.title ? <span className="text-sm text-text-secondary">{String(config.title)}</span> : null}
      </div>
    )
  }

  if (kind === 'table') {
    const columns = (config.columns as string[]) ?? []
    const rows = (config.rows as unknown[][]) ?? []
    return (
      <div className="overflow-auto" style={{ height }}>
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-background-card">
            <tr className="border-b border-border">
              {columns.map((c) => (
                <th key={c} className="text-left py-2 px-3 text-text-secondary font-medium">{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i} className="border-b border-border/40">
                {row.map((cell, j) => (
                  <td key={j} className="py-1.5 px-3 text-text-primary">{String(cell ?? '')}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }

  return <EChartWrapper option={config} height={height} />
}
