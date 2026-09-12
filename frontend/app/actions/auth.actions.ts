"use server";

import {
  type ActionResult,
  type LoginPayload,
  clearAuthCookies,
  mirrorAuthCookiesFromResponse,
  normaliseActionError,
  serverFetch,
} from "@/lib/auth/auth.server";
import type { Principal } from "@/types";

interface RawPrincipal {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  principal_type: "user" | "admin";
  roles: string[];
  company?: string;
  avatar_url?: string;
}

function toPrincipal(raw: RawPrincipal): Principal {
  return {
    id: raw.id,
    email: raw.email,
    first_name: raw.first_name,
    last_name: raw.last_name,
    principal_type: raw.principal_type,
    roles: raw.roles,
    company: raw.company,
    avatar_url: raw.avatar_url,
  };
}

export async function loginAction(
  payload: LoginPayload
): Promise<ActionResult<Principal>> {
  try {
    const { data, response } = await serverFetch<{
      data: { principal: RawPrincipal };
    }>("/auth/login/", { body: payload });
    await mirrorAuthCookiesFromResponse(response);
    return { ok: true, data: toPrincipal(data.data.principal) };
  } catch (error) {
    return { ok: false, error: normaliseActionError(error) };
  }
}

export async function registerAction(payload: {
  email: string;
  password: string;
  first_name: string;
  last_name: string;
  company?: string;
}): Promise<ActionResult<Principal>> {
  try {
    const { data, response } = await serverFetch<{
      data: { principal: RawPrincipal };
    }>("/auth/register/", { body: payload });
    await mirrorAuthCookiesFromResponse(response);
    return { ok: true, data: toPrincipal(data.data.principal) };
  } catch (error) {
    return { ok: false, error: normaliseActionError(error) };
  }
}

export async function logoutAction(): Promise<void> {
  try {
    await serverFetch("/auth/logout/", { withAuth: true });
  } catch {
    // Always clear cookies regardless of API outcome.
  } finally {
    await clearAuthCookies();
  }
}
