'use client'

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { FileText, Download, Plus, Loader2, Trash2 } from 'lucide-react'
import { reportService, datasetService } from '@/lib/api/services'
import { SkeletonCard } from '@/components/common/loading-page'
import { useUIStore } from '@/store/use-ui-store'

export default function ReportsPage() {
  const qc = useQueryClient()
  const { addToast } = useUIStore()
  const [selectedDs, setSelectedDs] = useState('')
  const [reportName, setReportName] = useState('')

  const reportsQ = useQuery({
    queryKey: ['reports'],
    queryFn: () => reportService.list(),
    // Poll while any report is still generating so status flips to ready.
    refetchInterval: (query) =>
      (query.state.data?.reports ?? []).some((r) => r.status === 'generating') ? 3000 : false,
  })
  const datasetsQ = useQuery({ queryKey: ['datasets'], queryFn: () => datasetService.list() })

  const createMutation = useMutation({
    mutationFn: () => reportService.create({ dataset_id: selectedDs, name: reportName }),
    onSuccess: () => {
      addToast({ type: 'success', title: 'Report queued', message: 'Generating PDF in background…' })
      qc.invalidateQueries({ queryKey: ['reports'] })
      setReportName('')
    },
    onError: () => addToast({ type: 'error', title: 'Failed to create report' }),
  })

  const downloadMutation = useMutation({
    // Fetch the PDF through the API with auth cookies and save it —
    // presigned MinIO URLs are not reachable from the browser.
    mutationFn: ({ id, name }: { id: string; name: string }) => reportService.downloadFile(id, name),
    onError: () => addToast({ type: 'error', title: 'Download failed', message: 'Try again.' }),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => reportService.delete(id),
    onSuccess: () => {
      addToast({ type: 'success', title: 'Report deleted' })
      qc.invalidateQueries({ queryKey: ['reports'] })
    },
  })

  const reports = reportsQ.data?.reports ?? []
  const readyDatasets = (datasetsQ.data?.datasets ?? []).filter((d) => d.status === 'ready')

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text-primary">Reports</h1>
        <p className="text-text-secondary text-sm mt-1">Generate branded PDF reports from your datasets</p>
      </div>

      {/* Create form */}
      <div className="card space-y-4">
        <h2 className="text-sm font-semibold text-text-primary">New Report</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <input
            value={reportName}
            onChange={(e) => setReportName(e.target.value)}
            className="input-cyber"
            placeholder="Report name…"
          />
          <select
            value={selectedDs}
            onChange={(e) => setSelectedDs(e.target.value)}
            className="input-cyber"
          >
            <option value="">Select dataset…</option>
            {readyDatasets.map((ds) => (
              <option key={ds.id} value={ds.id}>{ds.name}</option>
            ))}
          </select>
          <button
            onClick={() => createMutation.mutate()}
            disabled={!selectedDs || !reportName || createMutation.isPending}
            className="btn-primary flex items-center justify-center gap-2 disabled:opacity-40"
          >
            {createMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
            Generate Report
          </button>
        </div>
      </div>

      {/* List */}
      {reportsQ.isLoading ? (
        <div className="space-y-3">{Array.from({ length: 3 }).map((_, i) => <SkeletonCard key={i} />)}</div>
      ) : reports.length === 0 ? (
        <div className="card text-center py-12 border-dashed">
          <FileText className="w-10 h-10 text-text-muted mx-auto mb-3" />
          <p className="text-text-secondary text-sm">No reports yet</p>
        </div>
      ) : (
        <div className="space-y-2">
          {reports.map((r) => (
            <div key={r.id} className="card flex items-center justify-between">
              <div className="flex items-center gap-3">
                <FileText className="w-4 h-4 text-neon-blue" />
                <div>
                  <p className="text-sm font-medium text-text-primary">{r.name}</p>
                  <p className="text-xs text-text-muted">
                    {r.generated_at
                      ? 'Generated ' + new Date(r.generated_at).toLocaleDateString()
                      : 'Created ' + new Date(r.created_at).toLocaleDateString()}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <span className={`text-xs font-medium ${r.status === 'ready' ? 'text-neon-green' : r.status === 'error' ? 'text-red-400' : 'text-yellow-400'}`}>
                  {r.status}
                </span>
                {r.status === 'ready' && r.has_download && (
                  <button
                    onClick={() => downloadMutation.mutate({ id: r.id, name: r.name })}
                    disabled={downloadMutation.isPending}
                    className="btn-ghost text-xs flex items-center gap-1 py-1.5 px-3"
                  >
                    <Download className="w-3.5 h-3.5" />
                    Download
                  </button>
                )}
                {r.status === 'generating' && <Loader2 className="w-4 h-4 text-text-muted animate-spin" />}
                <button onClick={() => deleteMutation.mutate(r.id)} className="text-text-muted hover:text-red-400">
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
