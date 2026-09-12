/**
 * middleware.ts
 * =============
 * Edge Middleware — JWT decode + silent refresh + role-based routing.
 * No signature verification here (FastAPI does that); we only read the payload.
 */

import { NextRequest, NextResponse } from 'next/server'

const ACCESS_COOKIE = 'access_token'
const REFRESH_COOKIE = 'refresh_token'

const PUBLIC_ROUTES = ['/', '/login', '/register']
const USER_ROUTES = ['/dashboard', '/datasets', '/builder', '/copilot', '/reports', '/profile']
const ADMIN_ROUTES = ['/admin']

interface JwtPayload {
  sub?: string
  principal_type?: 'user' | 'admin'
  roles?: string[]
  exp?: number
}

function decodeJwt(token: string): JwtPayload | null {
  try {
    const [, b64] = token.split('.')
    const padded = b64.replace(/-/g, '+').replace(/_/g, '/')
    return JSON.parse(atob(padded)) as JwtPayload
  } catch {
    return null
  }
}

function isExpired(payload: JwtPayload): boolean {
  if (!payload.exp) return true
  return Date.now() / 1000 > payload.exp - 10
}

async function silentRefresh(
  refreshToken: string,
): Promise<{ newAccess: string; newRefresh: string } | null> {
  try {
    const apiBase =
      process.env.API_INTERNAL_URL ??
      process.env.NEXT_PUBLIC_API_URL ??
      'http://localhost:8000/api/v1'

    const res = await fetch(`${apiBase}/auth/token/refresh/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Cookie: `${REFRESH_COOKIE}=${refreshToken}`,
      },
      body: JSON.stringify({}),
    })

    if (!res.ok) return null

    const setCookies: string[] =
      (res.headers as unknown as { getSetCookie?: () => string[] }).getSetCookie?.() ?? []

    let newAccess = ''
    let newRefresh = ''

    for (const raw of setCookies) {
      const [nameValue] = raw.split(';')
      const eq = nameValue.indexOf('=')
      const name = nameValue.slice(0, eq).trim()
      const value = nameValue.slice(eq + 1).trim()
      if (name === ACCESS_COOKIE) newAccess = value
      if (name === REFRESH_COOKIE) newRefresh = value
    }

    return newAccess ? { newAccess, newRefresh } : null
  } catch {
    return null
  }
}

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl

  // Skip static assets and API proxy routes.
  if (
    pathname.startsWith('/_next') ||
    pathname.startsWith('/api') ||
    pathname.includes('.')
  ) {
    return NextResponse.next()
  }

  const isPublic = PUBLIC_ROUTES.some((r) => pathname === r || pathname.startsWith(`${r}/`))
  const isUserRoute = USER_ROUTES.some((r) => pathname === r || pathname.startsWith(`${r}/`))
  const isAdminRoute = ADMIN_ROUTES.some((r) => pathname === r || pathname.startsWith(`${r}/`))

  const accessToken = request.cookies.get(ACCESS_COOKIE)?.value
  const refreshToken = request.cookies.get(REFRESH_COOKIE)?.value

  // Unauthenticated — no tokens at all.
  if (!accessToken && !refreshToken) {
    if (isPublic) return NextResponse.next()
    const url = new URL('/login', request.url)
    url.searchParams.set('from', pathname)
    return NextResponse.redirect(url)
  }

  let payload: JwtPayload | null = accessToken ? decodeJwt(accessToken) : null
  let response = NextResponse.next()

  // Access token expired — try silent refresh at the edge.
  if ((!payload || isExpired(payload)) && refreshToken) {
    const refreshed = await silentRefresh(refreshToken)
    if (refreshed) {
      payload = decodeJwt(refreshed.newAccess)
      const isProduction = process.env.NODE_ENV === 'production'
      response = NextResponse.next()
      response.cookies.set(ACCESS_COOKIE, refreshed.newAccess, {
        httpOnly: true,
        secure: isProduction,
        sameSite: 'lax',
        path: '/',
        maxAge: 60 * 15,
      })
      if (refreshed.newRefresh) {
        response.cookies.set(REFRESH_COOKIE, refreshed.newRefresh, {
          httpOnly: true,
          secure: isProduction,
          sameSite: 'lax',
          path: '/',
          maxAge: 60 * 60 * 24 * 7,
        })
      }
    } else if (!isPublic) {
      const res = NextResponse.redirect(new URL('/login?session=expired', request.url))
      res.cookies.delete(ACCESS_COOKIE)
      res.cookies.delete(REFRESH_COOKIE)
      return res
    }
  }

  if (payload && !isExpired(payload)) {
    // Already authenticated — redirect away from auth pages.
    if (isPublic && pathname !== '/') {
      const dest = payload.principal_type === 'admin' ? '/admin/dashboard' : '/dashboard'
      return NextResponse.redirect(new URL(dest, request.url))
    }

    // Role-based route guards.
    if (isAdminRoute && payload.principal_type !== 'admin') {
      return NextResponse.redirect(new URL('/dashboard', request.url))
    }
    if (isUserRoute && payload.principal_type !== 'user') {
      return NextResponse.redirect(new URL('/admin/dashboard', request.url))
    }

    return response
  }

  // Token undecodable and no refresh worked — clear and redirect.
  if (!isPublic) {
    const res = NextResponse.redirect(new URL('/login', request.url))
    res.cookies.delete(ACCESS_COOKIE)
    res.cookies.delete(REFRESH_COOKIE)
    return res
  }

  return response
}

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico).*)'],
}
