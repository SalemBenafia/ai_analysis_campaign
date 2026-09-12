'use client'

import { useDroppable } from '@dnd-kit/core'
import { X } from 'lucide-react'
import { cn } from '@/lib/utils'

interface ShelfProps {
  id: string
  label: string
  items: string[]
  labelFor: (name: string) => string
  onRemove: (name: string) => void
  hint?: string
  accent?: 'blue' | 'purple'
}

export function Shelf({ id, label, items, labelFor, onRemove, hint, accent = 'blue' }: ShelfProps) {
  const { setNodeRef, isOver } = useDroppable({ id })

  return (
    <div>
      <p className="text-[11px] uppercase tracking-wide text-text-muted mb-1">{label}</p>
      <div
        ref={setNodeRef}
        className={cn(
          'min-h-[42px] rounded-md border border-dashed border-border bg-background/40 p-1.5 flex flex-wrap gap-1.5 transition-colors',
          isOver && (accent === 'purple' ? 'border-neon-purple/60 bg-neon-purple/5' : 'border-neon-blue/60 bg-neon-blue/5'),
        )}
      >
        {items.length === 0 && (
          <span className="text-xs text-text-muted px-1 py-1">{hint || 'Drop a field here'}</span>
        )}
        {items.map((name) => (
          <span
            key={name}
            className={cn(
              'inline-flex items-center gap-1 px-2 py-1 rounded text-xs border',
              accent === 'purple' ? 'border-neon-purple/40 bg-neon-purple/10' : 'border-neon-blue/40 bg-neon-blue/10',
            )}
          >
            {labelFor(name)}
            <button onClick={() => onRemove(name)} className="text-text-muted hover:text-text-primary">
              <X className="w-3 h-3" />
            </button>
          </span>
        ))}
      </div>
    </div>
  )
}
