/** @type {import('next').NextConfig} */

// Content Security Policy, set as a static header.
// (Vercel Services doesn't support Edge middleware, so there is no per-request nonce. Next.js
// injects small inline bootstrap scripts, hence 'unsafe-inline' for scripts; every other source
// is still locked down.)
const dev = process.env.NODE_ENV !== "production";
const api = process.env.NEXT_PUBLIC_API_URL ?? ""; // empty = same origin, covered by 'self'
const supabase = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";

const csp = [
  `default-src 'self'`,
  `script-src 'self' 'unsafe-inline'${dev ? " 'unsafe-eval'" : ""}`,
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

const securityHeaders = [
  { key: "Content-Security-Policy", value: csp },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
  { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains; preload" },
  { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
];

const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // "standalone" is only used by the Docker image; Vercel builds its own output.
  ...(process.env.VERCEL ? {} : { output: "standalone" }),
  async headers() {
    return [
      { source: "/:path*", headers: securityHeaders },
      { source: "/auth/callback", headers: [{ key: "Cache-Control", value: "no-store" }, { key: "Referrer-Policy", value: "no-referrer" }] },
    ];
  },
};

export default nextConfig;
