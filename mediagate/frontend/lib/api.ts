"use client";

import { getSupabase, supabaseConfigured } from "./supabase";

// Empty = same origin. On Vercel (services), /api/* on the site's own domain routes to the backend.
// Set NEXT_PUBLIC_API_URL only when the API lives on another origin (e.g. http://localhost:8000 in dev).
export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details: unknown = null,
    public retryAfter: number | null = null,
  ) {
    super(message);
  }
}

async function accessToken(): Promise<string | null> {
  if (!supabaseConfigured()) return null;
  const { data } = await getSupabase().auth.getSession();
  return data.session?.access_token ?? null;
}

export async function api<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = await accessToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  let body = init.body;
  if (init.json !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(init.json);
  }
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, { ...init, headers, body, cache: "no-store" });
  } catch {
    throw new ApiError(0, "network_error", "Can't reach the server. Check your connection and try again.");
  }
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const err = data?.error ?? {};
    const retry = res.headers.get("retry-after");
    // No structured error body means the request never reached the app (crash, timeout, proxy).
    const fallback =
      res.status >= 500
        ? `The server couldn't handle this request (error ${res.status}). Please try again in a moment.`
        : `Request failed (${res.status}).`;
    throw new ApiError(
      res.status,
      err.code ?? (res.status >= 500 ? "server_unavailable" : "http_error"),
      err.message ?? fallback,
      err.details ?? null,
      retry ? Number(retry) : null,
    );
  }
  return data as T;
}
