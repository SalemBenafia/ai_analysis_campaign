'use client'

import { X, CheckCircle, AlertCircle, Info, AlertTriangle } from 'lucide-react'
import { useUIStore } from '@/store/use-ui-store'
import { cn } from '@/lib/utils'

const icons = {
  success: <CheckCircle className="w-4 h-4 text-neon-green" />,
  error: <AlertCircle className="w-4 h-4 text-red-400" />,
  info: <Info className="w-4 h-4 text-neon-blue" />,
  warning: <AlertTriangle className="w-4 h-4 text-yellow-400" />,
}

export function ToastContainer() {
  const { toasts, removeToast } = useUIStore()

  if (!toasts.length) return null

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm w-full pointer-events-none">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={cn(
            'glass rounded-xl px-4 py-3 flex items-start gap-3 shadow-card animate-in pointer-events-auto',
            t.type === 'error' ? 'border-red-500/30' : 'neon-border',
          )}
        >
          <span className="mt-0.5">{icons[t.type]}</span>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-text-primary">{t.title}</p>
            {t.message && <p className="text-xs text-text-secondary mt-0.5 truncate">{t.message}</p>}
          </div>
          <button
            onClick={() => removeToast(t.id)}
            className="text-text-muted hover:text-text-primary transition-colors ml-1 mt-0.5"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      ))}
    </div>
  )
}
