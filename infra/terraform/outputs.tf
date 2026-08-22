# outputs.tf - Values the app / operators need to wire settings.yaml after apply.
#
# These map onto config/settings.yaml / config.py fields so a deploy is just
# "apply, then export these into the runtime environment".

output "project_id" {
  description = "The deployment project id."
  value       = var.project_id
}

output "region" {
  description = "Pinned in-country residency region."
  value       = var.region
}

# --------------------------------- KMS -------------------------------------- #
output "kms_key" {
  description = "Regional CMEK crypto key id (binds BigQuery, Logging, Vertex AI, Cloud Run)."
  value       = google_kms_crypto_key.mkt_perf.id
}

# ------------------------------- Metrics warehouse -------------------------- #
output "bigquery_dataset" {
  description = "Metrics dataset id (config/settings.yaml bigquery.dataset)."
  value       = google_bigquery_dataset.mkt_performance.dataset_id
}

# ------------------------------- WORM logging ------------------------------- #
output "log_bucket" {
  description = "Locked WORM audit log bucket id (config/settings.yaml logging.bucket)."
  value       = google_logging_project_bucket_config.worm_audit.id
}

output "audit_sink_writer_identity" {
  description = "Sink writer identity (grant it bucket access if cross-project)."
  value       = google_logging_project_sink.audit_to_worm.writer_identity
}

# ----------------------------- Service / identity --------------------------- #
output "runtime_service_account" {
  description = "Cloud Run runtime service account email (Workload Identity, no keys)."
  value       = google_service_account.runtime.email
}

output "cloud_run_service" {
  description = "Cloud Run service name."
  value       = google_cloud_run_v2_service.api.name
}

output "cloud_run_uri" {
  description = "Cloud Run service URI (reachable via the internal load balancer)."
  value       = google_cloud_run_v2_service.api.uri
}
