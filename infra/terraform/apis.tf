# apis.tf - Enable exactly the managed services Mkt4 depends on.
#
# Guarantee map:
#   Managed-first / minimal surface: only the services the pinned gcp profile actually
#         binds (config/settings.yaml `adapters: ... gcp:`) are enabled - nothing speculative.
#   Residency: enabling these APIs is a prerequisite for the regional, CMEK-protected
#         resources defined in the sibling files.
#
# Service -> adapter that needs it (config/settings.yaml gcp bindings):
#   bigquery.googleapis.com   -> metrics  (BigQueryMetricsAdapter: the metrics warehouse)
#   aiplatform.googleapis.com -> ad_platform (VertexAdPlatformAdapter, Vertex AI forecasting),
#                                 llm (GeminiLLMAdapter), evaluation (GenAiEvalAdapter),
#                                 agent_registry (A2ARegistryAdapter)
#   modelarmor.googleapis.com -> guardrail (ModelArmorGuardrailAdapter)
#   logging.googleapis.com    -> audit (CloudLoggingAuditAdapter -> WORM bucket)
#   cloudtrace.googleapis.com -> tracer (CloudTraceTracerAdapter)
#   run.googleapis.com        -> the Cloud Run service that serves the FastAPI app
#
# NOTE on the ad platform: in the gcp profile the AdPlatformPort is backed by Vertex AI
# forecasting (a GCP API: aiplatform), so it needs no public egress. If a deployment instead
# points the AdPlatformPort at an EXTERNAL ad-network SaaS (Google Ads / Meta / etc.), that
# call leaves the perimeter over the internet and must be allowed as controlled egress
# (a VPC-SC egress rule or PSC), NOT by enabling a GCP API here.
#
# disable_on_destroy = false so a `terraform destroy` of this stack does not yank platform
# APIs out from under other workloads in a shared project.

locals {
  required_services = [
    "bigquery.googleapis.com",             # metrics warehouse (BigQueryMetricsAdapter)
    "aiplatform.googleapis.com",           # Vertex forecasting + Gemini + Gen AI eval + A2A
    "modelarmor.googleapis.com",           # Model Armor guardrail
    "logging.googleapis.com",              # Cloud Logging (WORM locked bucket + audit)
    "cloudtrace.googleapis.com",           # Cloud Trace (OpenTelemetry spans)
    "run.googleapis.com",                  # Cloud Run (serves the FastAPI app)
    "cloudkms.googleapis.com",             # Regional CMEK key ring
    "orgpolicy.googleapis.com",            # Org Policy residency constraints
    "accesscontextmanager.googleapis.com", # VPC Service Controls perimeter
    # Supporting services the above transitively require.
    "artifactregistry.googleapis.com", # hosts the Cloud Run container image (in-region)
    "compute.googleapis.com",          # VPC / networking for the perimeter
    "iam.googleapis.com",              # service accounts / least-privilege IAM
    "monitoring.googleapis.com",       # log-based metrics + alert policies
  ]
}

resource "google_project_service" "required" {
  for_each = toset(local.required_services)

  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}
