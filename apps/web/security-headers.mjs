/**
 * Security headers for every page (ROADMAP §5: CSP, HSTS, X-Frame-Options).
 *
 * Scripts: Next.js 14 renders inline bootstrap scripts without nonces, so 'unsafe-inline' stays
 * for scripts; everything else is limited to this origin, the API, and Vercel's preview toolbar.
 * The browser talks to the API directly (uploads, jobs), hence connect-src includes it.
 */
export function securityHeaders(apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000") {
  const api = new URL(apiUrl).origin;
  const vercel = "https://vercel.live";
  const csp = [
    "default-src 'self'",
    `script-src 'self' 'unsafe-inline' ${vercel}`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob: https://vercel.com https://vercel.live",
    "font-src 'self' data:",
    `connect-src 'self' ${api} ${vercel} wss://ws-us3.pusher.com`,
    `frame-src ${vercel}`,
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self' https://github.com",
    "object-src 'none'",
  ].join("; ");
  return [
    { key: "Content-Security-Policy", value: csp },
    { key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" },
    { key: "X-Frame-Options", value: "DENY" },
    { key: "X-Content-Type-Options", value: "nosniff" },
    { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
    { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
  ];
}
