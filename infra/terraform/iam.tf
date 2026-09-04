# iam.tf - Least-privilege runtime service account for the Cloud Run service.
#
# Guarantee map:
#   Least privilege: a single dedicated serving identity with only the roles the gcp-profile
#         adapters need - read the metrics warehouse, call Vertex / Gemini / eval, call Model
#         Armor, write audit + traces. No "kitchen-sink" SA, no exportable keys (org policy
#         forbids them; Cloud Run uses this SA via Workload Identity).
#   Residency: identity is project-scoped; data access is to in-region services only.
#   CMEK (explicit): the SA gets its own cryptoKey use binding for envelope ops it performs.

resource "google_service_account" "runtime" {
  account_id   = "mkt-performance-runtime"
  display_name = "performance-marketing-optimisation Performance Marketing - Cloud Run runtime"
  project      = var.project_id

  depends_on = [google_project_service.required]
}

locals {
  # Serving path roles, each tied to a gcp-profile adapter:
  #   bigquery.dataViewer + jobUser -> MetricsPort (read the warehouse, run query jobs)
  #   aiplatform.user               -> AdPlatformPort (forecasting), LlmPort (Gemini),
  #                                    EvaluationGatePort (Gen AI eval), AgentRegistryPort (A2A)
  #   modelarmor.user               -> GuardrailPort (Model Armor)
  #   logging.logWriter             -> AuditSinkPort (write audit events to the WORM sink)
  #   cloudtrace.agent              -> ObservabilityTracerPort (spans, content OFF)
  #   monitoring.metricWriter       -> emit custom metrics
  runtime_roles = [
    "roles/bigquery.dataViewer",
    "roles/bigquery.jobUser",
    "roles/aiplatform.user",
    "roles/modelarmor.user",
    "roles/logging.logWriter",
    "roles/cloudtrace.agent",
    "roles/monitoring.metricWriter",
  ]
}

resource "google_project_iam_member" "runtime" {
  for_each = toset(local.runtime_roles)
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.runtime.email}"
}

# The runtime uses the CMEK for envelope ops it performs directly.
resource "google_kms_crypto_key_iam_member" "runtime" {
  crypto_key_id = google_kms_crypto_key.mkt_perf.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:${google_service_account.runtime.email}"
}
