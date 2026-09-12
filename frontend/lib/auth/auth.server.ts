import "server-only";

/**
 * Server-side auth utilities.
 * Uses API_INTERNAL_URL (Docker bridge) so login never crosses browser CORS.
 * Mirrors HttpOnly cookies from FastAPI into Next.js cookie store.
 */

import { cookies } from "next/headers";

export const API_BASE =
  process.env.API_INTERNAL_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  "http://backend:8000/api/v1";

export const ACCESS_COOKIE = "access_token";
export const REFRESH_COOKIE = "refresh_token";

export type ActionResult<T = void> =
  | { ok: true; data: T }
  | { ok: false; error: NormalisedError };

export interface NormalisedError {
  message: string;
  fieldErrors: Record<string, string>;
  code?: string;
  status?: number;
}

export interface LoginPayload {
  email: string;
  password: string;
}

interface FetchOpts {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  body?: unknown;
  withAuth?: boolean;
}

export async function serverFetch<T>(
  path: string,
  { method = "POST", body, withAuth = false }: FetchOpts = {}
): Promise<{ data: T; response: Response }> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };

  if (withAuth) {
    const store = await cookies();
    const cookieHeader = store
      .getAll()
      .map((c) => `${c.name}=${c.value}`)
      .join("; ");
    if (cookieHeader) headers["Cookie"] = cookieHeader;
  }

  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
    cache: "no-store",
  });

  if (!res.ok) {
    const json = await res.json().catch(() => ({}));
    throw { response: { data: json, status: res.status } };
  }

  const text = await res.text();
  const data = text ? (JSON.parse(text) as T) : ({} as T);
  return { data, response: res };
}

export async function mirrorAuthCookiesFromResponse(res: Response): Promise<void> {
  const setCookies: string[] =
    (res.headers as unknown as { getSetCookie?: () => string[] }).getSetCookie?.() ?? [];

  if (setCookies.length === 0) {
    const single = res.headers.get("set-cookie");
    if (single) setCookies.push(single);
  }

  const store = await cookies();
  const isProduction = process.env.NODE_ENV === "production";

  for (const raw of setCookies) {
    const [nameValue] = raw.split(";");
    const eq = nameValue.indexOf("=");
    const name = nameValue.slice(0, eq).trim();
    const value = nameValue.slice(eq + 1).trim();

    if (name === ACCESS_COOKIE || name === REFRESH_COOKIE) {
      store.set(name, value, {
        httpOnly: true,
        secure: isProduction,
        sameSite: "lax",
        path: "/",
        maxAge: name === ACCESS_COOKIE ? 60 * 15 : 60 * 60 * 24 * 7,
      });
    }
  }
}

export async function clearAuthCookies(): Promise<void> {
  const store = await cookies();
  store.delete(ACCESS_COOKIE);
  store.delete(REFRESH_COOKIE);
}

export interface JwtPayload {
  sub?: string;
  principal_type?: "user" | "admin";
  roles?: string[];
  exp?: number;
  type?: string;
}

export function decodeJwtPayload(token: string): JwtPayload | null {
  try {
    const [, b64] = token.split(".");
    const padded = b64.replace(/-/g, "+").replace(/_/g, "/");
    return JSON.parse(atob(padded)) as JwtPayload;
  } catch {
    return null;
  }
}

export function isTokenExpired(payload: JwtPayload): boolean {
  if (!payload.exp) return true;
  return Date.now() / 1000 > payload.exp - 10;
}

export function normaliseActionError(error: unknown): NormalisedError {
  if (!error || typeof error !== "object") {
    return { message: "Unexpected error occurred.", fieldErrors: {} };
  }
  const err = error as {
    response?: {
      data?: {
        error?: { code?: string; message?: string };
        detail?: string | Array<{ msg?: string; loc?: unknown[] }>;
      };
      status?: number;
    };
  };
  if (!err.response?.data) {
    return {
      message: "Network error. Please try again.",
      fieldErrors: {},
      status: err.response?.status,
    };
  }
  const d = err.response.data;

  let message = "Something went wrong.";
  if (d.error?.message) {
    message = d.error.message;
  } else if (typeof d.detail === "string") {
    message = d.detail;
  } else if (Array.isArray(d.detail) && d.detail.length > 0) {
    // Pydantic validation errors: [{msg, loc, type, ...}]
    message = d.detail.map((e) => e.msg ?? "Validation error").join(". ");
  }

  return {
    message,
    fieldErrors: {},
    code: d.error?.code,
    status: err.response?.status,
  };
}
