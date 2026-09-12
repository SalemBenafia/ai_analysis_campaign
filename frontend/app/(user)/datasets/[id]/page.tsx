'use client'

import { useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, MessageSquare, Wand2 } from 'lucide-react'
import Link from 'next/link'
import { datasetService, analyticsService, copilotService } from '@/lib/api/services'
import { LoadingPage } from '@/components/common/loading-page'
import { PreviewTable } from '@/components/features/datasets/preview-table'
import { TimeSeriesTab, AnomaliesTab, CompareTab } from '@/components/features/datasets/analysis-tabs'
import { SemanticEditor } from '@/components/features/datasets/semantic-editor'
import { formatNumber, formatBytes, cn } from '@/lib/utils'

const TABS = ['Overview', 'Preview', 'Time Series', 'Anomalies', 'Compare', 'Semantic Model'] as const
type Tab = (typeof TABS)[number]

export default function DatasetDetailPage() {
  const { id } = useParams<{ id: string }>()
  const router = useRouter()
  const [tab, setTab] = useState<Tab>('Overview')

  const dsQ = useQuery({ queryKey: ['dataset', id], queryFn: () => datasetService.get(id), enabled: !!id })
  const kpisQ = useQuery({
    queryKey: ['kpis', id],
    queryFn: () => analyticsService.kpis(id),
    enabled: dsQ.data?.dataset?.status === 'ready',
  })

  if (dsQ.isLoading) return <LoadingPage />
  const ds = dsQ.data?.dataset
  const cols = dsQ.data?.columns ?? []
  const kpis = kpisQ.data?.kpis ?? {}
  if (!ds) return null

  const ready = ds.status === 'ready'
  const startCopilot = async () => {
    const { conversation_id } = await copilotService.start(id)
    router.push('/copilot?conv=' + conversation_id)
  }
  const sumKpis = Object.entries(kpis).filter(([k]) => k.endsWith('_sum')).slice(0, 6)

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-5">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-3">
          <Link href="/datasets" className="text-text-muted hover:text-text-primary"><ArrowLeft className="w-5 h-5" /></Link>
          <div>
            <h1 className="text-xl font-bold text-text-primary">{ds.name}</h1>
            <p className="text-text-secondary text-sm">
              {formatBytes(ds.file_size_bytes)} · {ds.row_count ? formatNumber(ds.row_count) + ' rows' : 'Processing…'} · {ds.file_format.toUpperCase()}
            </p>
          </div>
        </div>
        {ready && (
          <div className="flex gap-2">
            <button onClick={startCopilot} className="btn-primary flex items-center gap-2 text-sm"><MessageSquare className="w-4 h-4" /> Ask AI</button>
            <Link href={`/builder?dataset=${id}`} className="btn-ghost flex items-center gap-2 text-sm"><Wand2 className="w-4 h-4" /> Build</Link>
          </div>
        )}
      </div>

      {!ready ? (
        <div className="card text-center py-16 text-text-muted">
          Dataset is {ds.status}. Analysis tools appear once processing completes.
        </div>
      ) : (
        <>
          <div className="flex gap-1 border-b border-border overflow-x-auto">
            {TABS.map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={cn('px-3 py-2 text-sm whitespace-nowrap border-b-2 -mb-px transition-colors',
                  tab === t ? 'border-neon-blue text-neon-blue' : 'border-transparent text-text-muted hover:text-text-primary')}
              >
                {t}
              </button>
            ))}
          </div>

          {tab === 'Overview' && (
            <div className="space-y-5">
              {sumKpis.length > 0 && (
                <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                  {sumKpis.map(([key, val]) => (
                    <div key={key} className="stat-card">
                      <div className="stat-label">{key.replace('_sum', '').replace(/_/g, ' ')}</div>
                      <div className="stat-value">{formatNumber(Number(val))}</div>
                    </div>
                  ))}
                </div>
              )}
              <div className="card overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-border">
                      <th className="text-left py-2 px-3 text-text-muted">Column</th>
                      <th className="text-left py-2 px-3 text-text-muted">Type</th>
                      <th className="text-left py-2 px-3 text-text-muted">Role</th>
                      <th className="text-left py-2 px-3 text-text-muted">Sample</th>
                    </tr>
                  </thead>
                  <tbody>
                    {cols.map((col) => (
                      <tr key={col.name} className="border-b border-border/40">
                        <td className="py-2 px-3 font-mono text-text-primary">{col.name}</td>
                        <td className="py-2 px-3 text-text-muted">{col.col_type}</td>
                        <td className="py-2 px-3">
                          {col.is_metric && <span className="text-neon-blue mr-2">metric</span>}
                          {col.is_dimension && <span className="text-neon-purple">dimension</span>}
                        </td>
                        <td className="py-2 px-3 text-text-muted truncate max-w-xs">{col.sample_values.slice(0, 3).join(', ')}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
          {tab === 'Preview' && <PreviewTable datasetId={id} />}
          {tab === 'Time Series' && <TimeSeriesTab datasetId={id} cols={cols} />}
          {tab === 'Anomalies' && <AnomaliesTab datasetId={id} cols={cols} />}
          {tab === 'Compare' && <CompareTab datasetId={id} cols={cols} />}
          {tab === 'Semantic Model' && <SemanticEditor datasetId={id} cols={cols} />}
        </>
      )}
    </div>
  )
}
