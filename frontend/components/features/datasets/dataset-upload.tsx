'use client'

import { useCallback } from 'react'
import { useDropzone } from 'react-dropzone'
import { Upload, FileSpreadsheet } from 'lucide-react'
import { cn } from '@/lib/utils'
import { formatBytes } from '@/lib/utils'

interface DatasetUploadProps {
  onFile: (file: File) => void
  loading?: boolean
}

const ACCEPTED = {
  'text/csv': ['.csv'],
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
  'application/json': ['.json'],
  'application/octet-stream': ['.parquet'],
}

export function DatasetUpload({ onFile, loading = false }: DatasetUploadProps) {
  const onDrop = useCallback(
    (accepted: File[]) => {
      if (accepted[0]) onFile(accepted[0])
    },
    [onFile],
  )

  const { getRootProps, getInputProps, isDragActive, acceptedFiles } = useDropzone({
    onDrop,
    accept: ACCEPTED,
    maxFiles: 1,
    maxSize: 50 * 1024 * 1024,
    disabled: loading,
  })

  const file = acceptedFiles[0]

  return (
    <div
      {...getRootProps()}
      className={cn(
        'border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all duration-200',
        isDragActive
          ? 'border-neon-blue bg-neon-blue/5'
          : 'border-border hover:border-neon-blue/40 hover:bg-background-hover',
        loading && 'opacity-50 cursor-not-allowed',
      )}
    >
      <input {...getInputProps()} />
      <div className="flex flex-col items-center gap-3">
        {file ? (
          <>
            <FileSpreadsheet className="w-10 h-10 text-neon-blue" />
            <div>
              <p className="text-sm font-medium text-text-primary">{file.name}</p>
              <p className="text-xs text-text-muted">{formatBytes(file.size)}</p>
            </div>
          </>
        ) : (
          <>
            <Upload className={cn('w-10 h-10', isDragActive ? 'text-neon-blue' : 'text-text-muted')} />
            <div>
              <p className="text-sm font-medium text-text-primary">
                {isDragActive ? 'Drop your file here' : 'Drag & drop or click to upload'}
              </p>
              <p className="text-xs text-text-muted mt-1">CSV, XLSX, JSON, Parquet — max 50 MB</p>
            </div>
          </>
        )}
        {loading && (
          <div className="flex items-center gap-2 text-neon-blue text-sm">
            <div className="w-4 h-4 border-2 border-t-transparent border-neon-blue rounded-full animate-spin" />
            Uploading…
          </div>
        )}
      </div>
    </div>
  )
}
