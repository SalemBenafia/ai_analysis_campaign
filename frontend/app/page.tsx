'use client'

import Link from 'next/link'
import { ArrowRight, BarChart2, Brain, Database, Zap, Shield, TrendingUp } from 'lucide-react'

const FEATURES = [
  { icon: Database, title: 'Smart Ingestion', desc: 'Upload CSV, Excel, JSON, Parquet. Auto-detect schema and metrics.' },
  { icon: BarChart2, title: 'Semantic Analytics', desc: 'Cube-powered semantic layer. Define ROAS, CTR, CPA once — reuse everywhere.' },
  { icon: Brain, title: 'AI Copilot', desc: 'Ask questions in plain English. A Groq-powered agent answers with real data.' },
  { icon: Zap, title: 'Drag & Drop Builder', desc: 'Build charts and dashboards visually, or let AI create insights for you.' },
  { icon: TrendingUp, title: 'Automated Reports', desc: 'Generate and schedule branded PDF reports for your team.' },
  { icon: Shield, title: 'Secure by Design', desc: 'HttpOnly cookies, RBAC, parameterized SQL, per-tenant isolation.' },
]

export default function LandingPage() {
  return (
    <main className="min-h-screen bg-background overflow-hidden">
      {/* Hero */}
      <section className="relative h-screen flex items-center justify-center bg-grid">
        <div className="pointer-events-none absolute inset-0 overflow-hidden">
          <div className="absolute -top-40 left-1/2 -translate-x-1/2 h-[42rem] w-[42rem] rounded-full bg-neon-blue/20 blur-[120px]" />
          <div className="absolute top-1/3 -right-32 h-[28rem] w-[28rem] rounded-full bg-neon-purple/20 blur-[120px]" />
          <div className="absolute -bottom-32 -left-24 h-[26rem] w-[26rem] rounded-full bg-neon-green/10 blur-[120px]" />
        </div>
        <div className="relative z-10 text-center px-4 max-w-4xl mx-auto animate-in">
          <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full border border-neon-blue/30 bg-neon-blue/5 text-neon-blue text-xs font-medium mb-8">
            <Zap className="w-3 h-3" />
            AI-Powered Meta Ads Intelligence
          </div>
          <h1 className="text-5xl md:text-7xl font-bold tracking-tight leading-none mb-6">
            <span className="text-text-primary">Transform your</span>
            <br />
            <span className="text-gradient">campaign data</span>
            <br />
            <span className="text-text-primary">into insight</span>
          </h1>
          <p className="text-text-secondary text-lg md:text-xl max-w-2xl mx-auto mb-10 leading-relaxed">
            InsightAI automatically converts your Meta Ads data into dashboards, anomaly alerts,
            and conversational analytics — powered by a LangGraph AI copilot.
          </p>
          <div className="flex items-center justify-center gap-4 flex-wrap">
            <Link href="/register" className="btn-primary text-base px-8 py-3 flex items-center gap-2">
              Get started free
              <ArrowRight className="w-4 h-4" />
            </Link>
            <Link href="/login" className="btn-ghost text-base px-8 py-3">
              Sign in
            </Link>
          </div>
        </div>
        {/* Scroll indicator */}
        <div className="absolute bottom-8 left-1/2 -translate-x-1/2 flex flex-col items-center gap-2 text-text-muted text-xs">
          <div className="w-px h-8 bg-gradient-to-b from-transparent to-neon-blue/50" />
          <span>Scroll to explore</span>
        </div>
      </section>

      {/* Features */}
      <section className="py-24 px-4 max-w-6xl mx-auto">
        <div className="text-center mb-16">
          <h2 className="text-3xl md:text-4xl font-bold text-text-primary mb-4">
            Everything you need to{' '}
            <span className="text-gradient">analyze at scale</span>
          </h2>
          <p className="text-text-secondary max-w-xl mx-auto">
            Built for media buyers, performance marketers, and agencies who need speed and depth.
          </p>
        </div>
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
          {FEATURES.map(({ icon: Icon, title, desc }) => (
            <div key={title} className="card group hover:shadow-neon transition-all duration-300">
              <div className="w-10 h-10 rounded-lg bg-neon-blue/10 border border-neon-blue/20 flex items-center justify-center mb-4 group-hover:border-neon-blue/40 transition-colors">
                <Icon className="w-5 h-5 text-neon-blue" />
              </div>
              <h3 className="font-semibold text-text-primary mb-2">{title}</h3>
              <p className="text-sm text-text-secondary leading-relaxed">{desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* CTA */}
      <section className="py-24 px-4 text-center">
        <div className="max-w-2xl mx-auto card neon-border">
          <h2 className="text-2xl font-bold text-text-primary mb-3">Ready to see your data clearly?</h2>
          <p className="text-text-secondary mb-6">Start analyzing your Meta Ads campaigns in minutes.</p>
          <Link href="/register" className="btn-primary inline-flex items-center gap-2 text-base px-8 py-3">
            Start for free <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-border py-8 px-4 text-center text-text-muted text-sm">
        © 2025 InsightAI. All rights reserved.
      </footer>
    </main>
  )
}
