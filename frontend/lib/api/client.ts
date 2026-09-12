import axios from 'axios'
import type { ApiResponse } from '@/types'

const BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1'

export const apiClient = axios.create({
  baseURL: BASE,
  withCredentials: true,
  headers: { 'Content-Type': 'application/json' },
  timeout: 30_000,
})

let isRefreshing = false
let failedQueue: Array<{ resolve: (v: unknown) => void; reject: (e: unknown) => void }> = []

function processQueue(error: unknown) {
  failedQueue.forEach(({ resolve, reject }) => (error ? reject(error) : resolve(null)))
  failedQueue = []
}

apiClient.interceptors.response.use(
  (r) => r,
  async (error) => {
    const original = error.config
    const url = original.url ?? ''
    const isAuthEndpoint = url.includes('/auth/token/refresh/') || url.includes('/auth/login/')
    if (error.response?.status === 401 && !original._retry && !isAuthEndpoint) {
      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject })
        })
          .then(() => apiClient(original))
          .catch((e) => Promise.reject(e))
      }
      original._retry = true
      isRefreshing = true
      try {
        await apiClient.post('/auth/token/refresh/')
        processQueue(null)
        return apiClient(original)
      } catch (e) {
        processQueue(e)
        if (typeof window !== 'undefined') window.location.href = '/login'
        return Promise.reject(e)
      } finally {
        isRefreshing = false
      }
    }
    return Promise.reject(error)
  },
)

export async function get<T>(url: string, params?: Record<string, unknown>): Promise<T> {
  const r = await apiClient.get<ApiResponse<T>>(url, { params })
  return r.data.data
}

export async function post<T>(url: string, body?: unknown): Promise<T> {
  const r = await apiClient.post<ApiResponse<T>>(url, body)
  return r.data.data
}

export async function patch<T>(url: string, body?: unknown): Promise<T> {
  const r = await apiClient.patch<ApiResponse<T>>(url, body)
  return r.data.data
}

export async function put<T>(url: string, body?: unknown): Promise<T> {
  const r = await apiClient.put<ApiResponse<T>>(url, body)
  return r.data.data
}

export async function del<T>(url: string): Promise<T> {
  const r = await apiClient.delete<ApiResponse<T>>(url)
  return r.data.data
}

export async function upload<T>(url: string, file: File, extraFields?: Record<string, string>): Promise<T> {
  const form = new FormData()
  form.append('file', file)
  if (extraFields) Object.entries(extraFields).forEach(([k, v]) => form.append(k, v))
  const r = await apiClient.post<ApiResponse<T>>(url, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return r.data.data
}
