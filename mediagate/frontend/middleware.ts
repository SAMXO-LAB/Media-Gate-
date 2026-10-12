import { NextResponse, type NextRequest } from "next/server";

// Per-request nonce-based Content Security Policy. Next.js applies the nonce to its own scripts.
export function middleware(request: NextRequest) {
  const nonce = btoa(crypto.randomUUID());
  const api = process.env.NEXT_PUBLIC_API_URL ?? ""; // empty = same origin, covered by 'self'

  const supabase = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";
  const dev = process.env.NODE_ENV !== "production";

  const csp = [
    `default-src 'self'`,
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${dev ? " 'unsafe-eval'" : ""}`,
    `style-src 'self' 'unsafe-inline'`,
    // Thumbnails are loaded directly from platform CDNs returned by official APIs.
    `img-src 'self' data: blob: https://i.ytimg.com https://*.cdninstagram.com https://*.fbcdn.net https://pbs.twimg.com`,
    `font-src 'self'`,
    `connect-src 'self' ${api} ${supabase} ${supabase.replace("https://", "wss://")}`.replace(/\s+/g, " ").trim(),
    `frame-ancestors 'none'`,
    `base-uri 'self'`,
    `form-action 'self'`,
    `object-src 'none'`,
    dev ? "" : "upgrade-insecure-requests",
  ]
    .filter(Boolean)
    .join("; ");

  const headers = new Headers(request.headers);
  headers.set("x-nonce", nonce);
  headers.set("Content-Security-Policy", csp);
  const response = NextResponse.next({ request: { headers } });
  response.headers.set("Content-Security-Policy", csp);
  return response;
}

export const config = {
  matcher: [{ source: "/((?!_next/static|_next/image|favicon.ico|icon.svg).*)" }],
};
