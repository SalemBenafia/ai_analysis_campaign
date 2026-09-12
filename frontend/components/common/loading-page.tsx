export function LoadingPage() {
  return (
    <div className="min-h-screen bg-background flex items-center justify-center">
      <div className="flex flex-col items-center gap-4">
        <div className="relative w-12 h-12">
          <div className="absolute inset-0 rounded-full border-2 border-neon-blue/20 animate-ping" />
          <div className="absolute inset-0 rounded-full border-2 border-t-neon-blue border-transparent animate-spin" />
        </div>
        <p className="text-text-secondary text-sm font-medium tracking-wider uppercase">Loading</p>
      </div>
    </div>
  )
}

export function LoadingSpinner({ size = 20 }: { size?: number }) {
  return (
    <div
      className="rounded-full border-2 border-t-neon-blue border-transparent animate-spin flex-shrink-0"
      style={{ width: size, height: size }}
    />
  )
}

export function SkeletonCard() {
  return (
    <div className="card space-y-3 animate-pulse">
      <div className="h-4 bg-background-hover rounded w-2/3" />
      <div className="h-8 bg-background-hover rounded w-1/2" />
      <div className="h-3 bg-background-hover rounded w-full" />
    </div>
  )
}
