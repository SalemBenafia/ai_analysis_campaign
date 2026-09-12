'use client'

import { FieldChip } from './field-chip'
import type { MemberCatalog } from '@/types'

export function FieldsPanel({ catalog }: { catalog: MemberCatalog }) {
  const computed = catalog.computed_metrics.map((m) => ({
    name: m.name, kind: 'computed' as const, title: m.display_name,
    type: 'number', description: m.description, format: m.format,
  }))

  return (
    <div className="space-y-4 overflow-y-auto">
      <div>
        <p className="text-[11px] uppercase tracking-wide text-text-muted mb-2">Dimensions</p>
        <div className="space-y-1.5">
          {catalog.dimensions.map((m) => <FieldChip key={m.name} member={m} />)}
        </div>
      </div>

      {computed.length > 0 && (
        <div>
          <p className="text-[11px] uppercase tracking-wide text-neon-purple mb-2">Computed Metrics</p>
          <div className="space-y-1.5">
            {computed.map((m) => <FieldChip key={m.name} member={m} />)}
          </div>
        </div>
      )}

      <div>
        <p className="text-[11px] uppercase tracking-wide text-text-muted mb-2">Measures</p>
        <div className="space-y-1.5">
          {catalog.measures.filter((m) => m.kind !== 'computed').map((m) => <FieldChip key={m.name} member={m} />)}
        </div>
      </div>
    </div>
  )
}
