import type { Metadata } from "next";
import "./globals.css";

// Required by the nonce CSP, not a performance preference. `proxy.ts` mints a per-request
// script nonce, and Next can only stamp it onto the script tags of a DYNAMICALLY rendered
// route. Prerendered HTML was built before the nonce existed, so nothing carries it, and
// because `'strict-dynamic'` switches off the `'self'` fallback the page ends up blocking
// strictly more than it did with no script policy at all. `next.config.mjs` refuses to build
// without this line; `scripts/assert-hydratable.mjs` proves the served document agrees.
export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Performance Marketing",
  description:
    "Cited performance reports (multi-touch attribution, ROAS / CAC, budget plan, A/B significance, anomalies), generic across banking and online retail and the JP/AU/SG markets.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // EMBED mode: the host page owns the chrome. When embedded (NEXT_PUBLIC_EMBED=1) we drop
  // the app-level banner so only the report console renders inside the host's iframe; the
  // standalone build keeps its own header.
  const embed = process.env.NEXT_PUBLIC_EMBED === "1";
  return (
    <html lang="en">
      <body className="min-h-screen">
        {embed ? (
          children
        ) : (
          <>
            <header className="border-b border-ink-200 bg-white">
              <div className="mx-auto max-w-6xl px-6 py-3">
                <span className="text-sm font-semibold text-ink-800">
                  Performance Marketing and Attribution
                </span>
                <span className="ml-2 text-xs text-ink-400">
                  synthetic data is fictional · JP / AU / SG
                </span>
              </div>
            </header>
            {children}
          </>
        )}
      </body>
    </html>
  );
}
