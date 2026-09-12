'use client'

import { useRef, useEffect, memo } from 'react'
import * as echarts from 'echarts/core'
import { BarChart, CandlestickChart, LineChart, PieChart, ScatterChart } from 'echarts/charts'
import {
  GridComponent, TooltipComponent, LegendComponent,
  TitleComponent, DataZoomComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { cn } from '@/lib/utils'

echarts.use([
  BarChart, CandlestickChart, LineChart, PieChart, ScatterChart,
  GridComponent, TooltipComponent, LegendComponent,
  TitleComponent, DataZoomComponent, CanvasRenderer,
])

interface EChartWrapperProps {
  option: Record<string, unknown>
  className?: string
  height?: number | string
}

export const EChartWrapper = memo(function EChartWrapper({
  option,
  className,
  height = 300,
}: EChartWrapperProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<echarts.ECharts | null>(null)

  useEffect(() => {
    if (!containerRef.current) return
    if (!chartRef.current) {
      chartRef.current = echarts.init(containerRef.current, null, { renderer: 'canvas' })
    }
    chartRef.current.setOption(option, true)
  }, [option])

  useEffect(() => {
    const observer = new ResizeObserver(() => chartRef.current?.resize())
    if (containerRef.current) observer.observe(containerRef.current)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    return () => {
      chartRef.current?.dispose()
      chartRef.current = null
    }
  }, [])

  return (
    <div
      ref={containerRef}
      className={cn('w-full', className)}
      style={{ height }}
    />
  )
})
