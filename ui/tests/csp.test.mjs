// Unit cover for `lib/csp.mjs`: exactly what a STRING can decide, and no more.
//
// These are NOT sufficient, and the distinction matters because the defect that shipped here was
// invisible to tests of this kind. A policy string can be perfect while the served page is dead
// markup: the header advertises a nonce, the route was statically prerendered so no script tag
// carries it, and `'strict-dynamic'` has switched off the `'self'` fallback, so the browser blocks
// every script. The header is byte-identical in the working and the broken case. Only
// `scripts/assert-hydratable.mjs`, which starts the built server and reads the served document,
// can tell them apart. What follows covers the half that is decidable from the string.

import assert from "node:assert/strict";
import { test } from "node:test";

import {
  DEFAULT_API_BASE,
  UnhydratableCspError,
  WildcardOriginError,
  assertHydratableCsp,
  contentSecurityPolicy,
  frameAncestors,
  frameOptions,
  generateNonce,
} from "../lib/csp.mjs";

/** Split a policy string into a directive map, the way a browser parses it. */
function directives(csp) {
  return new Map(
    csp
      .split(";")
      .map((part) => part.trim())
      .filter(Boolean)
      .map((part) => {
        const [name, ...value] = part.split(/\s+/);
        return [name.toLowerCase(), value.join(" ")];
      }),
  );
}

test("the policy carries every directive a default-deny posture needs", () => {
  const parsed = directives(contentSecurityPolicy({}, "n0nce"));
  for (const name of [
    "default-src",
    "base-uri",
    "form-action",
    "object-src",
    "script-src",
    "style-src",
    "img-src",
    "font-src",
    "connect-src",
    "frame-ancestors",
  ]) {
    assert.ok(parsed.has(name), `missing directive: ${name}`);
  }
  assert.equal(parsed.get("object-src"), "'none'");
  assert.equal(parsed.get("base-uri"), "'self'");
});

test("no directive is ever empty, in any state of the framing variable", () => {
  // An empty directive is a CSP parse error. Browsers discard the directive rather than the
  // policy, so `frame-ancestors` with no value removes the clickjacking restriction silently.
  for (const env of [{}, { NEXT_PUBLIC_FRAME_ANCESTORS: "" }, { NEXT_PUBLIC_FRAME_ANCESTORS: "  " }]) {
    for (const [name, value] of directives(contentSecurityPolicy(env, "n0nce"))) {
      assert.notEqual(value, "", `directive ${name} is empty for env ${JSON.stringify(env)}`);
    }
  }
});

test("script-src takes the nonce and strict-dynamic only when a nonce is passed", () => {
  const withNonce = directives(contentSecurityPolicy({}, "abc123")).get("script-src");
  assert.equal(withNonce, "'self' 'nonce-abc123' 'strict-dynamic'");

  // No nonce means the response is not a Next-rendered document, so no inline allowance at all.
  const without = directives(contentSecurityPolicy({})).get("script-src");
  assert.equal(without, "'self'");
  assert.ok(!without.includes("unsafe-inline"));
});

test("frame-ancestors is three-state, matching the service's own read", () => {
  // Unset keeps the shipped default.
  assert.equal(frameAncestors({}), "'self'");
  // Set but naming nothing means "nobody may frame this", spelled 'none', never an empty value.
  assert.equal(frameAncestors({ NEXT_PUBLIC_FRAME_ANCESTORS: "" }), "'none'");
  assert.equal(frameAncestors({ NEXT_PUBLIC_FRAME_ANCESTORS: "   " }), "'none'");
  // Named origins pass through, normalised.
  assert.equal(
    frameAncestors({ NEXT_PUBLIC_FRAME_ANCESTORS: "https://portal.bank.example  https://b.example" }),
    "https://portal.bank.example https://b.example",
  );
});

test("X-Frame-Options is emitted only for the two policies it can express", () => {
  assert.equal(frameOptions("'self'"), "SAMEORIGIN");
  assert.equal(frameOptions("'none'"), "DENY");
  // A named allowlist has no X-Frame-Options spelling, so sending one would contradict the CSP.
  assert.equal(frameOptions("https://portal.bank.example"), "");
});

test("connect-src widens to the API ORIGIN, not the full configured URL", () => {
  const parsed = directives(
    contentSecurityPolicy({ NEXT_PUBLIC_API_BASE: "https://api.example/v1/report?x=1" }, "n"),
  );
  assert.equal(parsed.get("connect-src"), "'self' https://api.example");
});

test("connect-src permits the same default the fetch client falls back to", () => {
  // The two must not be separate literals. When they disagree the console fetches an origin its
  // own policy forbids, and the only symptom is a blocked request in the browser console.
  const parsed = directives(contentSecurityPolicy({}, "n"));
  assert.equal(parsed.get("connect-src"), `'self' ${new URL(DEFAULT_API_BASE).origin}`);
});

test("a relative NEXT_PUBLIC_API_BASE is refused rather than silently dropped", () => {
  assert.throws(() => contentSecurityPolicy({ NEXT_PUBLIC_API_BASE: "/api" }, "n"), /absolute URL/);
});

test("nonces are unique and base64", () => {
  const seen = new Set();
  for (let i = 0; i < 50; i += 1) {
    const nonce = generateNonce();
    assert.match(nonce, /^[A-Za-z0-9+/]+={0,2}$/);
    assert.ok(!seen.has(nonce), "generateNonce repeated a value; a reused nonce is a guessable one");
    seen.add(nonce);
  }
});

test("the build refuses a layout that is not force-dynamic", () => {
  assert.throws(
    () => assertHydratableCsp("export const metadata = {};\n"),
    UnhydratableCspError,
  );
  assert.doesNotThrow(() => assertHydratableCsp('export const dynamic = "force-dynamic";\n'));
});

test("a wildcard frame-ancestors is refused in every spelling a config can render", () => {
  // The FastAPI half already refuses these. This is the OTHER emitter, and it is the one a
  // browser honours for the document, so closing only the service side left the console
  // framable by any origin while every check stayed green.
  for (const wildcard of ["*", "'*'", "null", "*.*"]) {
    assert.throws(
      () => frameAncestors({ NEXT_PUBLIC_FRAME_ANCESTORS: wildcard }),
      WildcardOriginError,
      `${JSON.stringify(wildcard)} must be refused, not passed through to the header`,
    );
  }
  assert.throws(
    () => frameAncestors({ NEXT_PUBLIC_FRAME_ANCESTORS: "https://portal.client.example *" }),
    WildcardOriginError,
    "a wildcard standing beside named origins is still a wildcard",
  );
  assert.throws(
    () => frameAncestors({ NEXT_PUBLIC_FRAME_ANCESTORS: "*,https://portal.client.example" }),
    WildcardOriginError,
    "a comma is not CSP list syntax, so a comma-joined wildcard must still be seen",
  );
  // A HOST-SOURCE wildcard is the spelling an exact-token set misses, and CSP honours it: every
  // subdomain may frame the console, including one an attacker takes over or registers on a
  // user-content domain. A real origin never contains an asterisk, so refusing the character
  // outright turns away nothing a deployment could correctly hold.
  for (const hostSource of [
    "https://*.client.example",
    "*.client.example",
    "https://*",
    "https://portal.client.example https://*.evil.example",
  ]) {
    assert.throws(
      () => frameAncestors({ NEXT_PUBLIC_FRAME_ANCESTORS: hostSource }),
      WildcardOriginError,
      `${JSON.stringify(hostSource)} is a host-source wildcard and must be refused`,
    );
  }
});

test("the policy the proxy actually serves refuses a wildcard too", () => {
  // `contentSecurityPolicy` is what `proxy.ts` puts on the document response. Refusing inside
  // the resolver alone would be theatre if this path could still build a policy around it.
  for (const wildcard of ["*", "'*'", "null", "*.*", "https://*.client.example"]) {
    assert.throws(
      () => contentSecurityPolicy({ NEXT_PUBLIC_FRAME_ANCESTORS: wildcard }, "n0nce"),
      WildcardOriginError,
      `the served document policy must not carry frame-ancestors ${wildcard}`,
    );
  }
});

test("a legitimate named allowlist is unaffected by the wildcard refusal", () => {
  // A refusal that also refuses valid input is an outage, not a control.
  assert.equal(
    frameAncestors({ NEXT_PUBLIC_FRAME_ANCESTORS: "https://portal.client.example" }),
    "https://portal.client.example",
  );
  assert.equal(
    frameAncestors({
      NEXT_PUBLIC_FRAME_ANCESTORS: "https://portal.client.example https://intranet.client.example",
    }),
    "https://portal.client.example https://intranet.client.example",
  );
  assert.equal(frameAncestors({ NEXT_PUBLIC_FRAME_ANCESTORS: "'self'" }), "'self'");
  assert.equal(frameAncestors({ NEXT_PUBLIC_FRAME_ANCESTORS: "'none'" }), "'none'");
  assert.match(
    contentSecurityPolicy({ NEXT_PUBLIC_FRAME_ANCESTORS: "https://portal.client.example" }, "n"),
    /frame-ancestors https:\/\/portal\.client\.example/,
  );
});

test("the unset and emptied states are exactly what they were before wildcards were refused", () => {
  // Pinned so a later edit cannot drift them. THIS repo maps an emptied value to 'none' rather
  // than refusing it, mirroring its own FastAPI half; the wildcard case is an addition to that
  // behaviour, never a replacement for it, and 'none' is the one answer a wildcard is not.
  assert.equal(frameAncestors({}), "'self'");
  for (const blank of ["", "   ", "\t", "\n", " \t\n "]) {
    assert.equal(
      frameAncestors({ NEXT_PUBLIC_FRAME_ANCESTORS: blank }),
      "'none'",
      `blank value ${JSON.stringify(blank)} must still resolve to the lockdown value`,
    );
  }
  assert.equal(frameOptions("'none'"), "DENY");
});
