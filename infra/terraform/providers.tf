# providers.tf - Provider pinning for the Mkt4 Performance Marketing sovereign deploy.
#
# Guarantee map (see SPEC.md "Guarantees"):
#   Residency / in-country: every provider call is pinned to the Singapore region
#         asia-southeast1. There is no global / multi-region default endpoint.
#   No lock-in: Terraform is the only place infrastructure is described; the app
#         itself talks to ports, not these resources.
#
# google-beta is required because a few resources (org_policy v2 surfaces, some Access
# Context Manager fields) are only exposed on the beta surface as of the pinned line.

terraform {
  required_version = ">= 1.9.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0" # 6.x line - current GA surface (mid-2026)
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 6.0"
    }
  }
}

# Primary (GA) provider - every resource defaults to Singapore.
provider "google" {
  project = var.project_id
  region  = var.region # asia-southeast1 (Singapore) - pinned, never global
}

# Beta provider - same project / region, used only where a resource needs it.
provider "google-beta" {
  project = var.project_id
  region  = var.region
}
