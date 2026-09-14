# bigquery.tf : the marketing-performance warehouse (metrics, journeys, series).
#
# Principle map:
#   Residency  : the dataset is created in var.region; account performance data stays there.
#   CMEK       : the dataset uses the regional CMEK from kms.tf (the BigQuery service-agent
#                key binding lives in kms.tf, because CMEK does not cascade).
#
# This schema is a CORRECTION, and the shape of the defect is worth recording because nothing
# offline could see it. The adapter that reads this dataset
# (adapters/gcp/bigquery_metrics.py) filters on `account_id` and `observed_date` and reads
# `impressions`, `clicks` and a nested `touchpoints` array. This file used to declare `date`,
# `touch_order` and no account column at all, so every query the managed profile makes would
# have failed at the first request on a deployment: an unknown column in the WHERE clause is
# not a subtle failure, and the local profile could not surface it because it ignored the
# account and never ran SQL.
#
# tests/contract/test_demo_book.py now parses this file and fails when the adapter reads a
# column it does not declare, or when the shipped book carries one it does not have.
#
# A journey is its ORDERED touchpoints, so they are a repeated record inside the journey row
# rather than one row per touch keyed by a separate order column. The attribution engine
# consumes a journey at a time; the previous shape would have made it reassemble what the
# warehouse had taken apart, and the adapter never did.
#
# scripts/load_demo_book.py fills these tables from the shipped fictional book, and refuses a
# dataset whose book_manifest does not declare itself fictional.

resource "google_bigquery_dataset" "mkt_performance" {
  dataset_id  = "mkt_performance" # matches settings.yaml bigquery.dataset
  project     = var.project_id
  location    = var.region
  description = "Marketing performance warehouse: channel metrics, conversion journeys, metric series (CMEK)."

  dynamic "default_encryption_configuration" {
    for_each = var.cmek_enabled ? [1] : []
    content {
      kms_key_name = one(google_kms_crypto_key.mkt_perf[*].id)
    }
  }

  delete_contents_on_destroy = false

  depends_on = [
    google_project_service.required,
    google_kms_crypto_key_iam_member.bigquery,
  ]
}

# Aggregated spend and outcome per account, channel and day. `impressions` and `clicks` are
# what the ROAS, CAC and bid engines divide by; without them the adapter read zeros and every
# derived rate would have been zero while the report still rendered.
resource "google_bigquery_table" "channel_metrics" {
  dataset_id          = google_bigquery_dataset.mkt_performance.dataset_id
  table_id            = "channel_metrics" # config/settings.yaml bigquery.metrics_table
  project             = var.project_id
  deletion_protection = true

  # The same key the dataset names, declared again here on purpose. The dataset's
  # default_encryption_configuration makes BigQuery stamp that key onto every table it creates in
  # the dataset, so the live table carries an encryption_configuration whether or not this
  # resource declares one. Leaving it undeclared makes the next plan read the server-set block as
  # a REMOVAL, and removing an encryption configuration FORCES REPLACEMENT: the table is destroyed
  # and recreated, and a recreated table holds no rows. CMEK does not cascade in Terraform's model
  # even though it does in BigQuery's, which is why the key is named twice.
  dynamic "encryption_configuration" {
    for_each = var.cmek_enabled ? [1] : []
    content {
      kms_key_name = one(google_kms_crypto_key.mkt_perf[*].id)
    }
  }

  schema = jsonencode([
    { name = "account_id", type = "STRING", mode = "REQUIRED" },
    { name = "market", type = "STRING", mode = "REQUIRED" },
    { name = "vertical", type = "STRING", mode = "REQUIRED" },
    { name = "channel", type = "STRING", mode = "REQUIRED" },
    { name = "spend", type = "FLOAT", mode = "REQUIRED" },
    { name = "impressions", type = "INTEGER", mode = "REQUIRED" },
    { name = "clicks", type = "INTEGER", mode = "REQUIRED" },
    { name = "conversions", type = "FLOAT", mode = "REQUIRED" },
    { name = "revenue", type = "FLOAT", mode = "REQUIRED" },
    { name = "observed_date", type = "DATE", mode = "REQUIRED" },
  ])
}

# One row per journey, its touchpoints nested and ordered by `position`.
resource "google_bigquery_table" "conversion_journeys" {
  dataset_id          = google_bigquery_dataset.mkt_performance.dataset_id
  table_id            = "conversion_journeys" # config/settings.yaml bigquery.journeys_table
  project             = var.project_id
  deletion_protection = true

  # The same key the dataset names, declared again here on purpose. The dataset's
  # default_encryption_configuration makes BigQuery stamp that key onto every table it creates in
  # the dataset, so the live table carries an encryption_configuration whether or not this
  # resource declares one. Leaving it undeclared makes the next plan read the server-set block as
  # a REMOVAL, and removing an encryption configuration FORCES REPLACEMENT: the table is destroyed
  # and recreated, and a recreated table holds no rows. CMEK does not cascade in Terraform's model
  # even though it does in BigQuery's, which is why the key is named twice.
  dynamic "encryption_configuration" {
    for_each = var.cmek_enabled ? [1] : []
    content {
      kms_key_name = one(google_kms_crypto_key.mkt_perf[*].id)
    }
  }

  schema = jsonencode([
    { name = "journey_id", type = "STRING", mode = "REQUIRED" },
    { name = "account_id", type = "STRING", mode = "REQUIRED" },
    { name = "market", type = "STRING", mode = "REQUIRED" },
    { name = "vertical", type = "STRING", mode = "REQUIRED" },
    { name = "converted", type = "BOOLEAN", mode = "REQUIRED" },
    { name = "revenue", type = "FLOAT", mode = "REQUIRED" },
    { name = "observed_date", type = "DATE", mode = "REQUIRED" },
    {
      name = "touchpoints", type = "RECORD", mode = "REPEATED",
      fields = [
        { name = "channel", type = "STRING", mode = "REQUIRED" },
        { name = "observed_date", type = "STRING", mode = "NULLABLE" },
        { name = "position", type = "INTEGER", mode = "REQUIRED" },
      ]
    },
  ])
}

# Dated scalar observations the anomaly detector runs over.
resource "google_bigquery_table" "metric_series" {
  dataset_id          = google_bigquery_dataset.mkt_performance.dataset_id
  table_id            = "metric_series" # config/settings.yaml bigquery.series_table
  project             = var.project_id
  deletion_protection = true

  # The same key the dataset names, declared again here on purpose. The dataset's
  # default_encryption_configuration makes BigQuery stamp that key onto every table it creates in
  # the dataset, so the live table carries an encryption_configuration whether or not this
  # resource declares one. Leaving it undeclared makes the next plan read the server-set block as
  # a REMOVAL, and removing an encryption configuration FORCES REPLACEMENT: the table is destroyed
  # and recreated, and a recreated table holds no rows. CMEK does not cascade in Terraform's model
  # even though it does in BigQuery's, which is why the key is named twice.
  dynamic "encryption_configuration" {
    for_each = var.cmek_enabled ? [1] : []
    content {
      kms_key_name = one(google_kms_crypto_key.mkt_perf[*].id)
    }
  }

  schema = jsonencode([
    { name = "account_id", type = "STRING", mode = "REQUIRED" },
    { name = "market", type = "STRING", mode = "REQUIRED" },
    { name = "vertical", type = "STRING", mode = "REQUIRED" },
    { name = "metric", type = "STRING", mode = "REQUIRED" },
    { name = "observed_date", type = "DATE", mode = "REQUIRED" },
    { name = "value", type = "FLOAT", mode = "REQUIRED" },
  ])
}

# What this dataset holds and whether it may be replaced. `fictional` is the loader's
# overwrite guard: a populated dataset without it is somebody's real warehouse and the loader
# refuses. Not deletion-protected, because the loader rewrites this row on every load and the
# guard is the control rather than the flag.
resource "google_bigquery_table" "book_manifest" {
  dataset_id          = google_bigquery_dataset.mkt_performance.dataset_id
  table_id            = "book_manifest"
  project             = var.project_id
  deletion_protection = false

  # The same key the dataset names, declared again here on purpose. The dataset's
  # default_encryption_configuration makes BigQuery stamp that key onto every table it creates in
  # the dataset, so the live table carries an encryption_configuration whether or not this
  # resource declares one. Leaving it undeclared makes the next plan read the server-set block as
  # a REMOVAL, and removing an encryption configuration FORCES REPLACEMENT: the table is destroyed
  # and recreated, and a recreated table holds no rows. CMEK does not cascade in Terraform's model
  # even though it does in BigQuery's, which is why the key is named twice.
  dynamic "encryption_configuration" {
    for_each = var.cmek_enabled ? [1] : []
    content {
      kms_key_name = one(google_kms_crypto_key.mkt_perf[*].id)
    }
  }

  schema = jsonencode([
    { name = "book_version", type = "STRING", mode = "REQUIRED" },
    { name = "as_of_date", type = "DATE", mode = "REQUIRED" },
    { name = "fictional", type = "BOOLEAN", mode = "REQUIRED" },
    { name = "loaded_at", type = "TIMESTAMP", mode = "NULLABLE" },
    { name = "source_commit", type = "STRING", mode = "NULLABLE" },
    { name = "tenant", type = "STRING", mode = "REQUIRED" },
  ])
}
