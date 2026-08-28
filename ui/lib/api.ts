/**
 * Typed fetch client for the D4 Performance Marketing FastAPI backend.
 *
 * Routes:
 *   POST /v1/report  -> PerformanceReport
 *   GET  /healthz    -> Health
 *
 * The API base is read from NEXT_PUBLIC_API_BASE, defaulting to DEFAULT_API_BASE (the D4 API
 * port) which is defined in lib/csp.mjs. The default lives THERE because the CSP's connect-src
 * has to permit exactly what this client fetches; as two separate literals they drifted the
 * moment one was edited, and the symptom is a blocked request with no explanation. All calls
 * are thin: the backend owns the business logic and the citations.
 */

import { DEFAULT_API_BASE } from "./csp.mjs";
import type {
  AttributionModelName,
  Health,
  Market,
  Persona,
  PerformanceReport,
  Vertical,
} from "./types";
import { ConfiguredEmptyError, readEnvValue } from "./env-setting.mjs";

// The API base is resolved in THREE states, not two.
//
// Reading `process.env.NEXT_PUBLIC_API_BASE?.replace(...) || "<loopback default>"`
// which hands a variable an operator DELIBERATELY EMPTIED the loopback default. That is a
// widening: the console then talks to a local API instead of the configured one, and
// `connect-src` is built from the same value, so the emptied deployment is byte-identical to one
// that never configured the variable. Next inlines NEXT_PUBLIC_* AT BUILD TIME, so the wrong
// value is frozen into the bundle and cannot be corrected at start-up.
// The literal member expression is required: a bundler substitutes the public value
// only where it sees exactly this, and handing it `process.env` leaves the browser
// reading {} and silently taking the hard-coded loopback default.
const API_BASE_SETTING = readEnvValue(
  "NEXT_PUBLIC_API_BASE",
  process.env.NEXT_PUBLIC_API_BASE,
);
if (API_BASE_SETTING.isConfiguredEmpty) {
  throw new ConfiguredEmptyError(
    "NEXT_PUBLIC_API_BASE is set to an empty value. An emptied variable names nothing, " +
      "so it cannot inherit the unset default (" + DEFAULT_API_BASE + "), which points this " +
      "console at a loopback API and widens connect-src to match. Unset it to take that " +
      "default deliberately, or give it the API origin this deployment should call.",
  );
}
export const API_BASE = (API_BASE_SETTING.hasValue ? API_BASE_SETTING.value : DEFAULT_API_BASE).replace(
  /\/+$/,
  "",
);

// Dev-only identity selection. In LOCAL mode the backend resolves identity from the
// X-Dev-Persona header; in secure profiles this is ignored (identity comes from an IAP
// assertion injected by the platform). The value is attached only when explicitly set.
let devPersona = "";

export function setDevPersona(id: string): void {
  devPersona = id;
}

export function getDevPersona(): string {
  return devPersona;
}

export class ApiError extends Error {
  status: number;
  body: string;
  constructor(message: string, status: number, body: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

export interface ReportBody {
  account_id: string;
  market: Market;
  vertical: Vertical;
  attribution_model?: AttributionModelName;
  lookback_days?: number;
}

function requestHeaders(): Record<string, string> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (devPersona) headers["X-Dev-Persona"] = devPersona;
  return headers;
}

async function parseJsonOrThrow(res: Response): Promise<unknown> {
  const text = await res.text();
  if (!res.ok) {
    let detail = text;
    try {
      const parsed = JSON.parse(text);
      detail = (parsed && (parsed.detail || parsed.message)) || text;
    } catch {
      /* keep raw text */
    }
    throw new ApiError(
      `${res.status} ${res.statusText}: ${detail || "request failed"}`,
      res.status,
      text,
    );
  }
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    throw new ApiError("Malformed JSON in response", res.status, text);
  }
}

export async function buildReport(
  body: ReportBody,
  signal?: AbortSignal,
): Promise<PerformanceReport> {
  const res = await fetch(`${API_BASE}/v1/report`, {
    method: "POST",
    headers: requestHeaders(),
    body: JSON.stringify(body),
    signal,
  });
  return (await parseJsonOrThrow(res)) as PerformanceReport;
}

export async function healthz(signal?: AbortSignal): Promise<Health | null> {
  try {
    const res = await fetch(`${API_BASE}/healthz`, {
      method: "GET",
      headers: requestHeaders(),
      signal,
    });
    if (!res.ok) return null;
    return (await res.json()) as Health;
  } catch {
    return null;
  }
}

export async function listPersonas(signal?: AbortSignal): Promise<Persona[]> {
  const res = await fetch(`${API_BASE}/v1/personas`, {
    method: "GET",
    headers: requestHeaders(),
    signal,
  });
  return (await parseJsonOrThrow(res)) as Persona[];
}

export const api = { buildReport, healthz, listPersonas };
