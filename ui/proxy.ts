// The one place a per-request CSP nonce is minted and attached. (Next 16 calls this file
// `proxy.ts`; it is the same interception point earlier versions called `middleware.ts`.)
//
// Both header sets below are required, and each is useless alone:
//
//   * on the REQUEST headers, because that is where Next reads the nonce it stamps onto every
//     script tag it emits. Without it the document's scripts carry no nonce and the browser
//     blocks them.
//   * on the RESPONSE headers, because that is the policy the browser actually enforces. Without
//     it there is no policy at all.
//
// The env values are read through LITERAL `process.env.NEXT_PUBLIC_*` accesses rather than by
// handing `process.env` to the policy module. Next substitutes `NEXT_PUBLIC_` variables at build
// time only where it can see the property name in the source; a dynamic read inside an imported
// module is not such a place, so passing the whole object would resolve to `undefined` in the edge
// runtime and collapse the three-state framing read back to its default without saying so.

import { type NextRequest, NextResponse } from "next/server";

import { contentSecurityPolicy, frameAncestors, frameOptions, generateNonce } from "./lib/csp.mjs";

const env = {
  NEXT_PUBLIC_FRAME_ANCESTORS: process.env.NEXT_PUBLIC_FRAME_ANCESTORS,
  NEXT_PUBLIC_API_BASE: process.env.NEXT_PUBLIC_API_BASE,
};

export function proxy(request: NextRequest) {
  const nonce = generateNonce();
  const csp = contentSecurityPolicy(env, nonce);

  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("Content-Security-Policy", csp);

  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set("Content-Security-Policy", csp);

  // The pre-CSP anti-clickjacking header, only for the two policies it can express.
  const legacy = frameOptions(frameAncestors(env));
  if (legacy) response.headers.set("X-Frame-Options", legacy);

  return response;
}

export const config = { matcher: "/:path*" };
