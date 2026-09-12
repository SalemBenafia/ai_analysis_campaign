'use client'

import { useEffect } from 'react'
import { AlertTriangle, RefreshCw } from 'lucide-react'

export default function Error({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error(error)
  }, [error])

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4">
      <div className="card max-w-md w-full text-center space-y-6">
        <div className="w-16 h-16 rounded-full bg-red-500/10 border border-red-500/30 flex items-center justify-center mx-auto">
          <AlertTriangle className="w-8 h-8 text-red-400" />
        </div>
        <div>
          <h2 className="text-xl font-semibold text-text-primary mb-2">Something went wrong</h2>
          <p className="text-text-secondary text-sm">{error.message || 'An unexpected error occurred.'}</p>
        </div>
        <button onClick={reset} className="btn-primary flex items-center gap-2 mx-auto">
          <RefreshCw className="w-4 h-4" />
          Try again
        </button>
      </div>
    </div>
  )
}
