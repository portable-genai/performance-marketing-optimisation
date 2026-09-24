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

variable "worm_locked" {
  description = <<-EOT
    Lock the WORM audit bucket. WARNING: LOCKING IS IRREVERSIBLE. With true, the bucket and its
    retention window can NEVER be reduced or deleted until every entry ages out, not even with
    project-owner rights. true is the compliant production form; false keeps the stack
    destroyable and is NOT compliant.

    There is deliberately NO DEFAULT. A plan refuses until the deployment names the lock,
    because an unset value may take a reviewed default and may never take an irreversible one.
    This stack used to hard-code the lock, so its first apply anywhere locked the bucket for the
    whole retention window with no way for a deployment to decline. Every stack that has this
    control spells it `worm_locked`, and none of them defaults it.
  EOT
  type        = bool
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

variable "manage_audit_config" {
  type        = bool
  default     = false
  description = <<-EOT
    Whether THIS stack writes the project's data-access audit configuration.

    False by default, and the default is the point. `google_project_iam_audit_config` is
    AUTHORITATIVE for the service it names, so a second stack declaring `allServices` does
    not add to that configuration, it REPLACES it, and a stack asking for DATA_READ and
    DATA_WRITE removes an ADMIN_READ a sibling enabled. Terraform reports that as a create
    rather than a change, because this stack holds no prior state for a resource that is
    nonetheless already live. Nearly every stack in this fleet carries this resource and one
    project hosts many of them, so a default of true is a race whose winner is whichever
    stack applied last.

    Data-access logs are also the highest-volume class Cloud Logging ingests, and nothing in
    the reference deployment reads them.

    Set true in exactly one stack per project, in that deployment's own tfvars, where the
    project genuinely wants data-access logging on.
  EOT
}

variable "posture_alerts_enabled" {
  type        = bool
  default     = false
  description = <<-EOT
    Whether this stack creates the posture alert policies and the log-based metrics behind
    them. False by default. Cloud Monitoring bills every metric-based alert condition, and a
    reference deployment that nobody pages gains nothing from them: the signals still land in
    Cloud Logging, where an operator can read them. Set true in a deployment with an on-call
    rota to notify, in that deployment's own tfvars.
  EOT
}

variable "cmek_enabled" {
  type        = bool
  default     = false
  description = <<-EOT
    Whether this stack creates its own Cloud KMS key ring and key and binds every store, log
    bucket and revision to it. False by default, and the default is the point: a key ring can
    never be deleted, a log bucket that has CMEK can never drop it, and registries and document
    stores take their key at creation. None of that changes an answer or a screen, and every
    resource is encrypted at rest with Google-managed keys regardless. A deployment with a
    customer whose data it must be able to shred, whose key access must be audited, or whose
    keys must live in an HSM sets this true in its own tfvars BEFORE its first apply. Flipping
    it off on a stack that already applied it is refused by the keys' prevent_destroy, which is
    the right answer: the stores it bound stay bound.
  EOT
}

# --------------------------------------------------------------------------- #
# Cheap runtime controls (the fleet's runtime-control contract). Each is on in the reference,
# reversible, and therefore takes a default; off is a stated deployment choice the service logs
# at startup.
# --------------------------------------------------------------------------- #
variable "guardrail_enabled" {
  description = "Switch the input and output guardrail (Model Armor under gcp) on the service (MKT_PERF_GUARDRAIL). A cheap runtime control: on in the reference, reversible, so it takes a default."
  type        = bool
  default     = true
}

variable "review_routing_enabled" {
  description = "Switch the hand-off of every report to the human-review-console (MKT_PERF_REVIEW_ROUTING). A cheap runtime control: on in the reference, reversible, so it takes a default."
  type        = bool
  default     = true
}

variable "human_review_url" {
  description = <<-EOT
    The human-review-console base URL the review router submits every report to
    (HUMAN_REVIEW_URL, rule R8). No default: with review routing on, the service refuses to
    boot without one, so a deployment names it or states review_routing_enabled = false (and
    then may pass ""). HTTPS, because the payload carries the report.
  EOT
  type        = string

  validation {
    condition     = !var.review_routing_enabled || can(regex("^https://", var.human_review_url))
    error_message = "review_routing_enabled requires human_review_url, an https:// URL: the service refuses to boot with routing on and no console named. Name one, or set review_routing_enabled = false."
  }

  validation {
    condition     = var.human_review_url == "" || can(regex("^https://", var.human_review_url))
    error_message = "human_review_url must be an https:// URL."
  }
}
