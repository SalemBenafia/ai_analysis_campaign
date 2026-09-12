'use client'

import { useRef, useEffect, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Send, Bot, User, BarChart2, Zap, Save, LayoutGrid } from 'lucide-react'
import { cn } from '@/lib/utils'
import { ChartRender } from '@/components/features/charts/chart-render'
import { AddToDashboardDialog } from '@/components/features/insights/add-to-dashboard-dialog'
import { copilotService } from '@/lib/api/services'
import { useUIStore } from '@/store/use-ui-store'
import type { CopilotMessage } from '@/types'

interface CopilotPanelProps {
  messages: CopilotMessage[]
  isSending: boolean
  onSend: (message: string) => void
  datasetName?: string
}

const QUICK_PROMPTS = [
  'What are the top performing campaigns?',
  'Show me spend vs conversions trend',
  'Which ad sets have the highest ROAS?',
  'Find anomalies in click-through rate',
]

export function CopilotPanel({ messages, isSending, onSend, datasetName }: CopilotPanelProps) {
  const [input, setInput] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = () => {
    const msg = input.trim()
    if (!msg || isSending) return
    setInput('')
    onSend(msg)
  }

  const handleKey = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="flex flex-col h-full">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 && (
          <div className="h-full flex flex-col items-center justify-center gap-6 text-center">
            <div className="w-16 h-16 rounded-full bg-neon-blue/10 border border-neon-blue/30 flex items-center justify-center">
              <Bot className="w-8 h-8 text-neon-blue" />
            </div>
            <div>
              <h3 className="text-lg font-semibold text-text-primary">AI Copilot</h3>
              {datasetName && (
                <p className="text-sm text-text-secondary mt-1">Analyzing: {datasetName}</p>
              )}
              <p className="text-xs text-text-muted mt-2">Ask anything about your campaign data</p>
            </div>
            <div className="grid grid-cols-2 gap-2 w-full max-w-sm">
              {QUICK_PROMPTS.map((p) => (
                <button
                  key={p}
                  onClick={() => onSend(p)}
                  className="text-left text-xs p-3 rounded-lg border border-border hover:border-neon-blue/40 hover:bg-background-hover text-text-secondary transition-all"
                >
                  {p}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg) => (
          <div
            key={msg.id}
            className={cn('flex gap-3', msg.role === 'user' ? 'flex-row-reverse' : 'flex-row')}
          >
            <div
              className={cn(
                'w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0',
                msg.role === 'user'
                  ? 'bg-neon-purple/20 border border-neon-purple/30'
                  : 'bg-neon-blue/10 border border-neon-blue/30',
              )}
            >
              {msg.role === 'user' ? (
                <User className="w-4 h-4 text-neon-purple" />
              ) : (
                <Bot className="w-4 h-4 text-neon-blue" />
              )}
            </div>
            <div className={cn('flex flex-col gap-2 max-w-[85%]', msg.role === 'user' && 'items-end')}>
              <div
                className={cn(
                  'rounded-xl px-4 py-3 text-sm',
                  msg.role === 'user'
                    ? 'bg-neon-purple/10 border border-neon-purple/20 text-text-primary'
                    : 'bg-background-card border border-border text-text-primary',
                )}
              >
                <p className="whitespace-pre-wrap leading-relaxed">{msg.content}</p>
              </div>
              {msg.echart_config && <MessageChart msg={msg} />}
              {msg.tool_calls && msg.tool_calls.length > 0 && (
                <div className="flex items-center gap-1 text-xs text-text-muted">
                  <Zap className="w-3 h-3 text-neon-blue" />
                  {msg.tool_calls.map((t) => (t as { tool: string }).tool).join(', ')}
                </div>
              )}
            </div>
          </div>
        ))}

        {isSending && (
          <div className="flex gap-3">
            <div className="w-8 h-8 rounded-full bg-neon-blue/10 border border-neon-blue/30 flex items-center justify-center">
              <Bot className="w-4 h-4 text-neon-blue" />
            </div>
            <div className="bg-background-card border border-border rounded-xl px-4 py-3">
              <div className="flex gap-1">
                {[0, 1, 2].map((i) => (
                  <div
                    key={i}
                    className="w-1.5 h-1.5 rounded-full bg-neon-blue animate-bounce"
                    style={{ animationDelay: i * 150 + 'ms' }}
                  />
                ))}
              </div>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="border-t border-border p-4" data-input>
        <div className="flex gap-2 items-end">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKey}
            placeholder="Ask about your data…"
            rows={1}
            className="input-cyber flex-1 resize-none max-h-32"
            style={{ minHeight: 44 }}
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || isSending}
            className="btn-primary flex items-center gap-2 flex-shrink-0 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <Send className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  )
}

function MessageChart({ msg }: { msg: CopilotMessage }) {
  const { addToast } = useUIStore()
  const [showAdd, setShowAdd] = useState(false)
  const [saved, setSaved] = useState(false)
  const canSave = !!msg.semantic_query

  const saveMutation = useMutation({
    mutationFn: () => copilotService.saveInsight(msg.id, msg.content.slice(0, 60) || 'Copilot insight'),
    onSuccess: () => { setSaved(true); addToast({ type: 'success', title: 'Saved as insight' }) },
    onError: () => addToast({ type: 'error', title: 'Could not save insight' }),
  })

  return (
    <div className="w-full rounded-xl border border-border bg-background-card p-3">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2 text-xs text-text-muted">
          <BarChart2 className="w-3 h-3" /> Visualization
        </div>
        {canSave && (
          <div className="flex items-center gap-2">
            <button onClick={() => saveMutation.mutate()} disabled={saved || saveMutation.isPending} className="flex items-center gap-1 text-xs text-text-muted hover:text-neon-blue disabled:opacity-40">
              <Save className="w-3.5 h-3.5" /> {saved ? 'Saved' : 'Save'}
            </button>
            <button onClick={() => setShowAdd(true)} className="flex items-center gap-1 text-xs text-text-muted hover:text-neon-blue">
              <LayoutGrid className="w-3.5 h-3.5" /> Dashboard
            </button>
          </div>
        )}
      </div>
      <ChartRender config={msg.echart_config as Record<string, unknown>} height={220} />
      {showAdd && <AddToDashboardDialog title={msg.content.slice(0, 40) || 'Chart'} messageId={msg.id} onClose={() => setShowAdd(false)} />}
    </div>
  )
}
