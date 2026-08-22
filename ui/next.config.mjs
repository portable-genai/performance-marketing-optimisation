import { readFileSync } from "node:fs";

import { assertHydratableCsp } from "./lib/csp.mjs";

/**
 * Refuse to build (or boot) a console whose CSP mints a nonce its HTML can never carry.
 *
 * `next build` and `next start` both evaluate this file, so the half-configured combination
 * (nonce in the policy, route statically prerendered) is caught here rather than shipped. That
 * combination blocks strictly MORE than the old policy did, because `'strict-dynamic'` switches
 * off the `'self'` fallback that was at least loading the chunk scripts, and it is invisible to
 * every check that does not execute the page.
 */
assertHydratableCsp(readFileSync(new URL("./app/layout.tsx", import.meta.url), "utf8"));

/** @type {import('next').NextConfig} */
const basePath = process.env.NEXT_PUBLIC_BASE_PATH || "";

const nextConfig = {
  reactStrictMode: true,
  ...(basePath ? { basePath, assetPrefix: basePath } : {}),
  async headers() {
    // The Content-Security-Policy is NOT here. It carries a per-request nonce, which a static
    // table cannot express, so `proxy.ts` sets it from `lib/csp.mjs`. Emitting one here as well
    // would give the browser two policies to intersect, per directive stricter wins, and the
    // static one has no nonce: the scripts would be blocked again. `X-Frame-Options` moved with
    // it, because it must agree with `frame-ancestors` and that now lives in one place too.
    // Only headers that are genuinely the same on every response belong here.
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "no-referrer" },
        ],
      },
    ];
  },
};

export default nextConfig;
