import type { Metadata, Viewport } from 'next'
import '@/styles/globals.css'
import { Providers } from '@/components/providers/providers'

export const metadata: Metadata = {
  title: { default: 'InsightAI', template: '%s | InsightAI' },
  description: 'AI-powered Meta Ads intelligence platform. Transform your campaign data into insights.',
  keywords: ['Meta Ads', 'AI analytics', 'Facebook Ads', 'performance marketing', 'BI platform'],
}

export const viewport: Viewport = {
  themeColor: '#0a0f1f',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
      </head>
      <body className="min-h-screen bg-background text-text-primary antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  )
}
