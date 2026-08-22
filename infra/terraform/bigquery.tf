# bigquery.tf - The performance-marketing-optimisation metrics warehouse (MetricsPort backend).
#
# Guarantee map:
#   Residency: the dataset location is var.region (the deployed market's region), so metrics
#         stay in-country.
#   CMEK (explicit, no cascade): the dataset is encrypted with the regional CMEK key (kms.tf).
#         Internal data only; there is no public surface to this dataset.
#
# Mirrors config/settings.yaml `bigquery:` (dataset + table names) so the
# BigQueryMetricsAdapter queries match what is provisioned. Rows are curated, fictional
# synthetic marketing metrics, never customer PII.

resource "google_bigquery_dataset" "mkt_performance" {
  dataset_id  = "mkt_performance" # config/settings.yaml bigquery.dataset
  location    = var.region        # in-country residency
  description = "Performance-marketing metrics warehouse for Mkt4 (channel metrics, conversion journeys, series)."

  default_encryption_configuration {
    kms_key_name = google_kms_crypto_key.mkt_perf.id
  }

  depends_on = [
    google_project_service.required,
    google_kms_crypto_key_iam_member.bigquery,
  ]
}

# channel_metrics - per-channel spend / conversions / revenue (ROAS, CAC inputs).
resource "google_bigquery_table" "channel_metrics" {
  dataset_id          = google_bigquery_dataset.mkt_performance.dataset_id
  table_id            = "channel_metrics" # config/settings.yaml bigquery.metrics_table
  deletion_protection = true

  encryption_configuration {
    kms_key_name = google_kms_crypto_key.mkt_perf.id
  }

  schema = jsonencode([
    { name = "date", type = "DATE", mode = "REQUIRED" },
    { name = "market", type = "STRING", mode = "REQUIRED" },
    { name = "vertical", type = "STRING", mode = "REQUIRED" },
    { name = "channel", type = "STRING", mode = "REQUIRED" },
    { name = "spend", type = "FLOAT", mode = "REQUIRED" },
    { name = "conversions", type = "INTEGER", mode = "REQUIRED" },
    { name = "revenue", type = "FLOAT", mode = "REQUIRED" },
  ])
}

# conversion_journeys - multi-touch paths feeding the attribution engine.
resource "google_bigquery_table" "conversion_journeys" {
  dataset_id          = google_bigquery_dataset.mkt_performance.dataset_id
  table_id            = "conversion_journeys" # config/settings.yaml bigquery.journeys_table
  deletion_protection = true

  encryption_configuration {
    kms_key_name = google_kms_crypto_key.mkt_perf.id
  }

  schema = jsonencode([
    { name = "journey_id", type = "STRING", mode = "REQUIRED" },
    { name = "market", type = "STRING", mode = "REQUIRED" },
    { name = "vertical", type = "STRING", mode = "REQUIRED" },
    { name = "touch_order", type = "INTEGER", mode = "REQUIRED" },
    { name = "channel", type = "STRING", mode = "REQUIRED" },
    { name = "converted", type = "BOOLEAN", mode = "REQUIRED" },
    { name = "value", type = "FLOAT", mode = "NULLABLE" },
  ])
}

# metric_series - time series feeding the anomaly-detection engine.
resource "google_bigquery_table" "metric_series" {
  dataset_id          = google_bigquery_dataset.mkt_performance.dataset_id
  table_id            = "metric_series" # config/settings.yaml bigquery.series_table
  deletion_protection = true

  encryption_configuration {
    kms_key_name = google_kms_crypto_key.mkt_perf.id
  }

  schema = jsonencode([
    { name = "date", type = "DATE", mode = "REQUIRED" },
    { name = "market", type = "STRING", mode = "REQUIRED" },
    { name = "metric", type = "STRING", mode = "REQUIRED" },
    { name = "value", type = "FLOAT", mode = "REQUIRED" },
  ])
}
