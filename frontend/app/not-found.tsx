import Link from 'next/link'

export default function NotFound() {
  return (
    <div className="min-h-screen bg-background bg-grid flex items-center justify-center p-4">
      <div className="text-center space-y-6">
        <div className="text-8xl font-bold text-gradient">404</div>
        <h2 className="text-2xl font-semibold text-text-primary">Page not found</h2>
        <p className="text-text-secondary max-w-sm">
          The page you are looking for does not exist or has been moved.
        </p>
        <Link href="/" className="btn-primary inline-flex">
          Go home
        </Link>
      </div>
    </div>
  )
}
