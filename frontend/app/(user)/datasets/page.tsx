'use client'

import Link from 'next/link'
import { Trash2, Database, RefreshCw } from 'lucide-react'
import { useDatasets } from '@/hooks/use-datasets'
import { DatasetUpload } from '@/components/features/datasets/dataset-upload'
import { formatBytes, formatNumber } from '@/lib/utils'
import { SkeletonCard } from '@/components/common/loading-page'
import type { Dataset } from '@/types'

function StatusBadge({ status }: { status: Dataset['status'] }) {
  const cls = {
    ready: 'text-neon-green',
    processing: 'text-yellow-400',
    error: 'text-red-400',
    uploading: 'text-neon-blue',
  }[status]
  return <span className={`text-xs font-medium ${cls}`}>{status}</span>
}

export default function DatasetsPage() {
  const { datasets, isLoading, upload, uploading, deleteDataset } = useDatasets()

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text-primary">Datasets</h1>
        <p className="text-text-secondary text-sm mt-1">Upload and manage your campaign data files</p>
      </div>

      <DatasetUpload onFile={upload} loading={uploading} />

      {isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => <SkeletonCard key={i} />)}
        </div>
      ) : datasets.length === 0 ? (
        <div className="card text-center py-16 border-dashed">
          <Database className="w-10 h-10 text-text-muted mx-auto mb-3" />
          <p className="text-text-secondary text-sm">Upload your first dataset above</p>
        </div>
      ) : (
        <div className="space-y-2">
          {datasets.map((ds) => (
            <div key={ds.id} className="card flex items-center justify-between group">
              <Link href={'/datasets/' + ds.id} className="flex items-center gap-3 flex-1 min-w-0">
                <Database className="w-4 h-4 text-neon-blue flex-shrink-0" />
                <div className="min-w-0">
                  <p className="text-sm font-medium text-text-primary group-hover:text-neon-blue transition-colors truncate">
                    {ds.name}
                  </p>
                  <p className="text-xs text-text-muted">
                    {formatBytes(ds.file_size_bytes)}
                    {ds.row_count ? ' · ' + formatNumber(ds.row_count) + ' rows' : ''}
                    {ds.column_count ? ' · ' + ds.column_count + ' cols' : ''}
                    {' · '}
                    {new Date(ds.created_at).toLocaleDateString()}
                  </p>
                </div>
              </Link>
              <div className="flex items-center gap-3 flex-shrink-0 ml-3">
                <StatusBadge status={ds.status} />
                {ds.status === 'processing' && (
                  <RefreshCw className="w-3.5 h-3.5 text-text-muted animate-spin" />
                )}
                <button
                  onClick={() => deleteDataset(ds.id)}
                  className="text-text-muted hover:text-red-400 transition-colors"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
