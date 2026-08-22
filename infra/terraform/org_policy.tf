# org_policy.tf - Org Policy constraints enforcing in-country residency and no SA keys.
#
# Guarantee map:
#   Residency (defence in depth): even if someone hand-edits a resource, gcp.resourceLocations
#         REJECTS the creation of resources outside the deployed market's region.
#   Least privilege: iam.disableServiceAccountKeyCreation forbids exportable SA keys; the
#         workloads use Workload Identity (the Cloud Run runtime SA) instead.
#
# Scoped to the project via parent = projects/<id>. To enforce org-wide, move these to an
# org-level policy with parent = "organizations/${var.org_id}".
# verify: https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/org_policy_policy

locals {
  # Map the deployed region to its gcp.resourceLocations value group.
  resource_location_group = {
    "asia-southeast1"      = "in:asia-southeast1-locations"
    "asia-northeast1"      = "in:asia-northeast1-locations"
    "australia-southeast1" = "in:australia-southeast1-locations"
  }[var.region]
}

# Master residency policy: only allow the deployed market's region.
resource "google_org_policy_policy" "resource_locations" {
  name   = "projects/${var.project_id}/policies/gcp.resourceLocations"
  parent = "projects/${var.project_id}"

  spec {
    rules {
      values {
        allowed_values = [local.resource_location_group]
      }
    }
  }

  depends_on = [google_project_service.required]
}

# Disable creation of exportable service-account keys (use Workload Identity instead).
resource "google_org_policy_policy" "disable_sa_keys" {
  name   = "projects/${var.project_id}/policies/iam.disableServiceAccountKeyCreation"
  parent = "projects/${var.project_id}"

  spec {
    rules {
      enforce = "TRUE"
    }
  }

  depends_on = [google_project_service.required]
}

# Require uniform bucket-level access (no per-object ACL exfiltration paths).
resource "google_org_policy_policy" "uniform_bucket_access" {
  name   = "projects/${var.project_id}/policies/storage.uniformBucketLevelAccess"
  parent = "projects/${var.project_id}"

  spec {
    rules {
      enforce = "TRUE"
    }
  }

  depends_on = [google_project_service.required]
}
