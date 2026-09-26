# model_armor.tftest.hcl : the guardrail template regional-capability gate (model_armor.tf).
#
# Both runs use mock providers and are plan-only, so the file runs with NO credentials, NO
# project and NO state beyond the provider download:
#
#   terraform init -backend=false && terraform test
#
# which is what `make tf-validate` runs. Nothing here is applied anywhere and every value is
# fictional.

mock_provider "google" {}
mock_provider "google-beta" {}

variables {
  project_id       = "fictional-mkt-perf-project"
  worm_locked      = false
  human_review_url = "https://review.fictional-bank.example"
}

run "asia_southeast1_declines_the_capabilities_the_region_refuses" {
  command = plan

  variables {
    region                        = "asia-southeast1"
    model_armor_full_capabilities = false
  }

  assert {
    condition = (
      length(google_model_armor_template.mkt_perf_guardrail.filter_config[0].malicious_uri_filter_settings) +
      length(google_model_armor_template.mkt_perf_guardrail.template_metadata[0].multi_language_detection)
    ) == 0
    error_message = "asia-southeast1 serves neither capability; model_armor_full_capabilities = false must be able to decline both, or the template is refused with CAPABILITY_NOT_SUPPORTED."
  }

  assert {
    condition     = google_model_armor_template.mkt_perf_guardrail.template_id == "mkt-perf-guardrail" && google_model_armor_template.mkt_perf_guardrail.location == var.region
    error_message = "The guardrail adapter screens through mkt-perf-guardrail (config/settings.yaml model_armor.template_id) in the deployment region; that template must be what this stack creates."
  }
}

run "the_default_deployment_gets_the_full_guardrail" {
  command = plan

  variables {
    region = "australia-southeast1" # a region that serves the full capability set
  }

  assert {
    condition = (
      length(google_model_armor_template.mkt_perf_guardrail.filter_config[0].malicious_uri_filter_settings) == 1 &&
      length(google_model_armor_template.mkt_perf_guardrail.template_metadata[0].multi_language_detection) == 1
    )
    error_message = "model_armor_full_capabilities defaults to true; a deployment outside the narrowed region must get the whole guardrail unless it opts out."
  }
}
