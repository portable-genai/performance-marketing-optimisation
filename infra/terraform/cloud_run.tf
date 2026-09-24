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
    encryption_key                   = one(google_kms_crypto_key.mkt_perf[*].id)
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

      # Cheap runtime controls, stated rather than inherited: on in the reference. Off is a
      # deployment choice the service logs at startup.
      env {
        name  = "MKT_PERF_GUARDRAIL"
        value = tostring(var.guardrail_enabled)
      }
      env {
        name  = "MKT_PERF_REVIEW_ROUTING"
        value = tostring(var.review_routing_enabled)
      }
      # Rule R8: the console every report is routed to. Set only when it carries a value,
      # because the service reads its environment in three states and an EMPTY variable is
      # refused. With routing on it is required (variables.tf), since the service refuses to
      # boot without it.
      dynamic "env" {
        for_each = var.human_review_url == "" ? [] : [var.human_review_url]
        content {
          name  = "HUMAN_REVIEW_URL"
          value = env.value
        }
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
