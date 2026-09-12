'use client'

import { useState, useEffect } from 'react'
import { useSearchParams } from 'next/navigation'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, MessageSquare } from 'lucide-react'
import { copilotService, datasetService } from '@/lib/api/services'
import { CopilotPanel } from '@/components/features/copilot/copilot-panel'
import { useCopilot } from '@/hooks/use-copilot'
import { cn } from '@/lib/utils'

export default function CopilotPage() {
  const searchParams = useSearchParams()
  const [activeConvId, setActiveConvId] = useState<string | null>(searchParams.get('conv'))
  const qc = useQueryClient()

  const { messages, isSending, send } = useCopilot(activeConvId)

  const convsQ = useQuery({
    queryKey: ['conversations'],
    queryFn: () => copilotService.list(),
  })

  const datasetsQ = useQuery({
    queryKey: ['datasets'],
    queryFn: () => datasetService.list(),
  })

  const startMutation = useMutation({
    mutationFn: (dataset_id: string) => copilotService.start(dataset_id),
    onSuccess: ({ conversation_id }) => {
      setActiveConvId(conversation_id)
      qc.invalidateQueries({ queryKey: ['conversations'] })
    },
  })

  const conversations = convsQ.data?.conversations ?? []
  const readyDatasets = (datasetsQ.data?.datasets ?? []).filter((d) => d.status === 'ready')
  const activeConv = conversations.find((c) => c.id === activeConvId)

  const [selectedDs, setSelectedDs] = useState('')

  return (
    <div className="flex h-full">
      {/* Sidebar */}
      <div className="w-64 border-r border-border flex flex-col flex-shrink-0 bg-background-secondary">
        <div className="p-4 border-b border-border">
          <h2 className="text-sm font-semibold text-text-primary mb-3">AI Copilot</h2>
          <div className="space-y-2">
            <select
              value={selectedDs}
              onChange={(e) => setSelectedDs(e.target.value)}
              className="input-cyber text-xs"
            >
              <option value="">Select dataset…</option>
              {readyDatasets.map((ds) => (
                <option key={ds.id} value={ds.id}>{ds.name}</option>
              ))}
            </select>
            <button
              onClick={() => selectedDs && startMutation.mutate(selectedDs)}
              disabled={!selectedDs || startMutation.isPending}
              className="btn-primary w-full text-xs flex items-center justify-center gap-1.5 py-2"
            >
              <Plus className="w-3.5 h-3.5" />
              New conversation
            </button>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {conversations.map((conv) => (
            <button
              key={conv.id}
              onClick={() => setActiveConvId(conv.id)}
              className={cn(
                'w-full text-left px-3 py-2.5 rounded-lg text-xs transition-all',
                conv.id === activeConvId
                  ? 'bg-neon-blue/10 text-neon-blue border border-neon-blue/20'
                  : 'text-text-secondary hover:bg-background-hover hover:text-text-primary',
              )}
            >
              <p className="font-medium truncate">{conv.title}</p>
              <p className="text-text-muted mt-0.5">{new Date(conv.created_at).toLocaleDateString()}</p>
            </button>
          ))}
        </div>
      </div>

      {/* Chat */}
      <div className="flex-1 overflow-hidden">
        {activeConvId ? (
          <CopilotPanel
            messages={messages}
            isSending={isSending}
            onSend={send}
            datasetName={activeConv?.title}
          />
        ) : (
          <div className="h-full flex items-center justify-center text-center p-8">
            <div>
              <MessageSquare className="w-12 h-12 text-text-muted mx-auto mb-4" />
              <p className="text-text-secondary text-sm">Select a dataset and start a new conversation</p>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
