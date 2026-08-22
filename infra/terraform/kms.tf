# kms.tf - Regional Customer-Managed Encryption Key (CMEK), in-region.
#
# Guarantee map:
#   CMEK does NOT cascade: a CMEK on one resource does not automatically protect data that
#         resource hands to another service. Each managed service (Logging, BigQuery, Vertex
#         AI, Cloud Run) must be told to use this key EXPLICITLY. We keep ONE regional key
#         ring + crypto key here and wire it into every resource that supports CMEK in its
#         own file.
#   Residency: the key ring location is var.region (the deployed market's region) - a
#         regional key, never the global / multi-region key. Regional CMEK pins crypto
#         material in-country.

resource "google_kms_key_ring" "mkt_perf" {
  name     = "mkt-performance-ring"
  location = var.region # in-country, regional key material

  depends_on = [google_project_service.required]
}

resource "google_kms_crypto_key" "mkt_perf" {
  name     = "mkt-performance-cmek"
  key_ring = google_kms_key_ring.mkt_perf.id

  purpose         = "ENCRYPT_DECRYPT"
  rotation_period = "7776000s" # 90 days - periodic rotation for key hygiene

  version_template {
    algorithm        = "GOOGLE_SYMMETRIC_ENCRYPTION"
    protection_level = "SOFTWARE"
  }

  lifecycle {
    # A destroyed key is unrecoverable and would strand all CMEK-encrypted data.
    prevent_destroy = true
  }
}

# --------------------------------------------------------------------------- #
# Grant each service agent the right to use the key. CMEK does not cascade:
# every service that encrypts with this key needs its OWN binding here.
# --------------------------------------------------------------------------- #
data "google_project" "this" {
  project_id = var.project_id
}

# Cloud Logging service agent (CMEK on the WORM bucket).
resource "google_kms_crypto_key_iam_member" "logging" {
  crypto_key_id = google_kms_crypto_key.mkt_perf.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:service-${data.google_project.this.number}@gcp-sa-logging.iam.gserviceaccount.com"
}

# BigQuery service agent (CMEK on the metrics dataset / tables).
resource "google_kms_crypto_key_iam_member" "bigquery" {
  crypto_key_id = google_kms_crypto_key.mkt_perf.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:bq-${data.google_project.this.number}@bigquery-encryption.iam.gserviceaccount.com"
}

# Vertex AI service agent (CMEK on Gemini / forecasting / eval state).
resource "google_kms_crypto_key_iam_member" "aiplatform" {
  crypto_key_id = google_kms_crypto_key.mkt_perf.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:service-${data.google_project.this.number}@gcp-sa-aiplatform.iam.gserviceaccount.com"
}

# Cloud Run service agent (CMEK on the service revision).
resource "google_kms_crypto_key_iam_member" "run" {
  crypto_key_id = google_kms_crypto_key.mkt_perf.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:service-${data.google_project.this.number}@serverless-robot-prod.iam.gserviceaccount.com"
}
