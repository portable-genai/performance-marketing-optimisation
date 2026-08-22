/**
 * Domain shapes mirrored from the D4 FastAPI backend (the JSON shape of a cited
 * PerformanceReport produced by `to_jsonable`).
 */

export type Market = "JP" | "AU" | "SG";
export type Vertical = "banking" | "online_retail";
export type AttributionModelName =
  | "last_touch"
  | "first_touch"
  | "linear"
  | "position_based";

export interface Citation {
  source_id: string;
  source_type: string;
  title: string;
  url?: string;
  page?: number | null;
  observed_date?: string | null;
  snippet?: string;
  score?: number | null;
}

export interface ChannelAttribution {
  channel: string;
  attributed_conversions: number;
  attributed_revenue: number;
  credit_share: number;
  citations: Citation[];
}

export interface AttributionView {
  model: string;
  market: Market;
  vertical: Vertical;
  channels: ChannelAttribution[];
  total_conversions: number;
  total_revenue: number;
  journeys_considered: number;
}

export interface ChannelEfficiency {
  channel: string;
  spend: number;
  revenue: number;
  conversions: number;
  roas: number;
  cac: number;
  meets_roas_target: boolean;
  meets_cac_target: boolean;
  citations: Citation[];
}

export interface EfficiencyReport {
  market: Market;
  vertical: Vertical;
  channels: ChannelEfficiency[];
  blended_roas: number;
  blended_cac: number;
}

export interface BudgetShift {
  channel: string;
  direction: string;
  current_budget: number;
  proposed_budget: number;
  delta: number;
  rationale?: string;
  severity: string;
  citations: Citation[];
}

export interface BudgetPlan {
  market: Market;
  vertical: Vertical;
  shifts: BudgetShift[];
  total_budget: number;
}

export interface AbResult {
  test_id: string;
  metric: string;
  control_rate: number;
  variant_rate: number;
  absolute_lift: number;
  relative_lift: number;
  z_score: number;
  p_value: number;
  significant: boolean;
  verdict: string;
  rationale?: string;
  citations: Citation[];
}

export interface Anomaly {
  metric: string;
  observed_date: string;
  value: number;
  baseline: number;
  deviation: number;
  kind: string;
  severity: string;
  rationale?: string;
  citations: Citation[];
}

export interface AnomalyReport {
  market: Market;
  vertical: Vertical;
  anomalies: Anomaly[];
}

export interface PerformanceReport {
  id: string;
  account_id: string;
  market: Market;
  vertical: Vertical;
  summary: string;
  attribution: AttributionView | null;
  efficiency: EfficiencyReport | null;
  budget_plan: BudgetPlan | null;
  ab_results: AbResult[];
  anomalies: AnomalyReport | null;
  citations: Citation[];
  requires_human_review: boolean;
}

export interface Health {
  status: string;
  profile: string;
  market: string;
  vertical: string;
}

// A seeded local dev persona (from GET /v1/personas), used by the demo identity picker.
// Local profile only; secure profiles resolve identity from the IAP assertion.
export interface Persona {
  id: string;
  subject: string;
  tenant: string;
  principals: string;
}
