# variables.tf - The only knobs. Everything else is a concrete in-region value.
#
# Guarantee map (SPEC.md "Guarantees"):
#   Residency: `region` defaults to asia-southeast1 (Singapore, the SG market's residency
#         region) and is validated so a caller cannot accidentally point this stack at a
#         non-Singapore region. The app validates the same per-market allow-list at settings
#         load (config.market_profile), so the control is enforced in code AND in infra.
#   Auditability / retention: `retention_days` is a Terraform variable (the WORM bucket lock
#         is irreversible, so retention must be deliberate). Mirrors
#         config/settings.yaml logging.retention_days.
#
# NOTE on markets: performance-marketing-optimisation is APAC-generic (JP / AU / SG). This stack deploys ONE market per
# project; the SG default (asia-southeast1) is the reference. Deploying JP or AU is a separate
# project with its own residency region (asia-northeast1 / australia-southeast1) and its own
# allow-list value below.

variable "project_id" {
  description = "Target GCP project id (required). Single-tenant, single-market, in-country."
  type        = string
}

variable "region" {
  description = "Deployment region. Pinned to a supported APAC residency region; validated to fail fast."
  type        = string
  default     = "asia-southeast1" # SG market (Singapore)

  validation {
    # The per-market residency allow-list, identical to config/settings.yaml markets.*.region
    # and config.market_profile(): SG -> asia-southeast1, JP -> asia-northeast1,
    # AU -> australia-southeast1. Any other region is rejected at plan time.
    condition     = contains(["asia-southeast1", "asia-northeast1", "australia-southeast1"], var.region)
    error_message = "performance-marketing-optimisation is an APAC-resident deployment: region must be one of asia-southeast1 (SG), asia-northeast1 (JP) or australia-southeast1 (AU)."
  }
}

variable "retention_days" {
  description = "WORM audit-log retention in days. Default ~7 years. Lock is irreversible."
  type        = number
  default     = 2557 # ~7 years; mirrors config/settings.yaml logging.retention_days

  validation {
    condition     = var.retention_days >= 2557
    error_message = "Compliance retention must be at least 2557 days (~7 years)."
  }
}

variable "org_id" {
  description = "Organization id - required for org-wide Org Policy and Access Context Manager."
  type        = string
  default     = ""
}

variable "access_policy_id" {
  description = <<-EOT
    Existing Access Context Manager policy id (numeric, no prefix) for the org.
    Required when enable_vpc_sc = true; the service perimeter is created under it.
    Create once per org with:
      gcloud access-context-manager policies create \
        --organization=ORG_ID --title="apac-residency"
  EOT
  type        = string
  default     = ""
}

variable "enable_vpc_sc" {
  description = "Create the VPC Service Controls perimeter around the AI / data APIs (dry-run first)."
  type        = bool
  default     = false
}

variable "vpc_sc_dry_run" {
  description = "When true, the perimeter is created in dry-run (audit-only) mode; flip to false to enforce after a clean dry-run window."
  type        = bool
  default     = true
}

variable "container_image" {
  description = "Fully-qualified image for the Cloud Run service (Artifact Registry, asia-southeast1)."
  type        = string
  default     = "asia-southeast1-docker.pkg.dev/REPLACE_WITH_PROJECT/mkt/performance-marketing-optimisation:0.1.0"
}

variable "alert_notification_channels" {
  description = "Monitoring notification channel ids to attach to the posture alert policies. Empty still creates the policies."
  type        = list(string)
  default     = []
}
