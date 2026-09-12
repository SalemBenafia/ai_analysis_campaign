'use client'

import { useDraggable } from '@dnd-kit/core'
import { Hash, Calendar, Type, FunctionSquare } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { SemanticMember } from '@/types'

export function fieldIcon(member: SemanticMember) {
  if (member.kind === 'computed') return FunctionSquare
  if (member.type === 'time') return Calendar
  if (member.kind === 'measure') return Hash
  return Type
}

export function FieldChip({ member }: { member: SemanticMember }) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: `field:${member.kind}:${member.name}`,
    data: { member },
  })
  const Icon = fieldIcon(member)

  return (
    <div
      ref={setNodeRef}
      {...listeners}
      {...attributes}
      className={cn(
        'flex items-center gap-2 px-2.5 py-1.5 rounded-md border border-border bg-background-card text-xs cursor-grab active:cursor-grabbing select-none hover:border-neon-blue/40 transition-colors',
        isDragging && 'opacity-40',
        member.kind === 'computed' && 'border-neon-purple/40',
      )}
      title={member.description || member.title}
    >
      <Icon className={cn('w-3.5 h-3.5', member.kind === 'measure' && 'text-neon-blue', member.kind === 'computed' && 'text-neon-purple', member.kind === 'dimension' && 'text-text-muted')} />
      <span className="text-text-primary truncate">{member.title}</span>
      {member.kind === 'computed' && <span className="text-[10px] text-neon-purple ml-auto">fx</span>}
      {member.kind === 'measure' && member.agg == null && <span className="text-[10px] text-text-muted ml-auto">raw</span>}
    </div>
  )
}
