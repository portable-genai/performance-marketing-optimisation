# cloud_run.tf - Cloud Run v2 service running the performance-marketing-optimisation FastAPI app.
#
# Runs as the dedicated least-privilege runtime identity (iam.tf, Workload Identity, no keys),
# encrypted with the regional CMEK key (kms.tf), in-region. Environment variables drive the
# settings.yaml ${ENV:-default} interpolation, so no code or config file changes between
# environments. The image sets MKT_PERF_PROFILE=gcp EXPLICITLY (an unset variable is "no
# choice", which binds the SDK-free adapters and refuses every end-user request, so
# production must set it here).
#
# Guarantee map:
#   Residency: location = var.region; the image lives in an in-region Artifact Registry.
#   CMEK: the revision is encrypted with the regional key.
#   Minimal surface: internal + load-balancer ingress only - no open public ingress.

resource "google_cloud_run_v2_service" "api" {
  name     = "performance-marketing-optimisation"
  location = var.region
  project  = var.project_id

  # Internal + load-balancer ingress only - the service is reached through the platform
  # load balancer, not the open internet.
  ingress = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"

  template {
    # Encrypt the revision with the regional CMEK key.
    encryption_key                   = google_kms_crypto_key.mkt_perf.id
    service_account                  = google_service_account.runtime.email
    max_instance_request_concurrency = 80

    scaling {
      min_instance_count = 1
      max_instance_count = 4
    }

    containers {
      image = var.container_image

      ports {
        container_port = 8103
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }

      # Opt in to the managed stack explicitly (an unset variable is refused, not `local`).
      env {
        name  = "MKT_PERF_PROFILE"
        value = "gcp"
      }
      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }
      env {
        name  = "MKT_SETTINGS"
        value = "/app/config/settings.yaml"
      }

      startup_probe {
        http_get {
          path = "/healthz"
          port = 8103
        }
        initial_delay_seconds = 5
        period_seconds        = 5
        failure_threshold     = 6
      }

      liveness_probe {
        http_get {
          path = "/healthz"
          port = 8103
        }
        period_seconds = 30
      }
    }
  }

  depends_on = [
    google_kms_crypto_key_iam_member.run,
    google_project_iam_member.runtime,
  ]
}
