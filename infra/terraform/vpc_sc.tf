# vpc_sc.tf - VPC Service Controls perimeter around the AI / data plane.
#
# Guarantee map:
#   Residency + exfiltration control: a service perimeter draws a logical boundary around the
#         sovereignty-critical APIs (BigQuery metrics, Vertex AI, Model Armor, Logging, KMS).
#         Data cannot be read across the boundary to an out-of-country project - which is what
#         stops the metrics and the audit log from leaving the market's region.
#
# Guarded by var.enable_vpc_sc (count = 0 lets non-prod / dev applies skip it).
#
# DRY-RUN FIRST (var.vpc_sc_dry_run, default true):
#   The perimeter is created in dry-run (audit-only) mode via the `spec {}` block plus
#   use_explicit_dry_run_spec = true. Calls that WOULD be denied are logged but allowed, so
#   you can confirm from the audit logs that no legitimate path breaks. Once the dry-run
#   window is clean, set vpc_sc_dry_run = false to move the config into the enforced `status {}`
#   block.
#
# DEPLOY-ORDER CAVEAT (enforced mode):
#   The enforced perimeter blocks API calls from outside it. Add your Terraform runner / CI
#   identity to an access level before enforcing, or the apply will be denied.

locals {
  perimeter_restricted_services = [
    "bigquery.googleapis.com",
    "aiplatform.googleapis.com",
    "modelarmor.googleapis.com",
    "logging.googleapis.com",
    "cloudtrace.googleapis.com",
    "cloudkms.googleapis.com",
    "run.googleapis.com",
  ]
}

resource "google_access_context_manager_service_perimeter" "mkt_perf" {
  count = var.enable_vpc_sc ? 1 : 0

  parent = "accessPolicies/${var.access_policy_id}"
  name   = "accessPolicies/${var.access_policy_id}/servicePerimeters/mkt_performance"
  title  = "mkt_performance"

  perimeter_type = "PERIMETER_TYPE_REGULAR"

  # Dry-run audit-only configuration (active while vpc_sc_dry_run = true).
  use_explicit_dry_run_spec = var.vpc_sc_dry_run

  dynamic "spec" {
    for_each = var.vpc_sc_dry_run ? [1] : []
    content {
      resources           = ["projects/${data.google_project.this.number}"]
      restricted_services = local.perimeter_restricted_services

      vpc_accessible_services {
        enable_restriction = true
        allowed_services   = local.perimeter_restricted_services
      }
    }
  }

  # Enforced configuration (active once vpc_sc_dry_run = false).
  dynamic "status" {
    for_each = var.vpc_sc_dry_run ? [] : [1]
    content {
      resources           = ["projects/${data.google_project.this.number}"]
      restricted_services = local.perimeter_restricted_services

      vpc_accessible_services {
        enable_restriction = true
        allowed_services   = local.perimeter_restricted_services
      }
    }
  }

  depends_on = [google_project_service.required]
}
