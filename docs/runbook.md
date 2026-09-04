# Runbook: `performance-marketing-optimisation` Stats-based Performance Marketing and Attribution

Operational notes for deploying and running `performance-marketing-optimisation` on the Gemini Enterprise Agent Platform in a
residency region (defaults `asia-southeast1`; JP and AU are per-market overrides). This is a
reference build; adapt it to your own change-management and model-risk sign-off before any live
use.

## 0. Profiles

`MKT_PERF_PROFILE` selects the adapter stack. It has **no default**: an unset (or blank)
variable is treated as "no profile was chosen", which binds the SDK-free adapters so the
process still boots but grants none of the local relaxations. The seeded dev personas are
refused (every end-user route answers 401) and the CORS dev origins are withheld. Name the
profile deliberately. An unknown or mis-capitalised value (`Local`, `GCP`) is refused outright
rather than silently selecting neither the relaxations nor the restrictions.

- `local` (SDK-free): the whole pipeline runs offline (deterministic statistics and
  LLM, in-memory metrics). No Google Cloud SDK. This is what CI and the demo run.
- `gcp`: the managed stack (BigQuery metrics, Vertex forecasting, Model Armor, Cloud Logging).
- `platform`: consume the shared Hrz services (guardrail / audit / eval / registry) over S2S.
- `onprem`: fail-fast placeholders that raise `NotImplementedError`, the migration target (see
  `docs/onprem-migration.md`).

`MKT_VERTICAL` (`banking` | `online_retail`) and `MKT_MARKET` (`JP` | `AU` | `SG`) select the
active vertical and market; the market's residency region and locales come from the per-market
profile in `config/settings.yaml`, never a hard-coded branch.

## 1. Offline demo and smoke (no cloud)

```bash
make demo          # build a cited report + render the static audit-first HTML into scripts/out
make smoke-local   # end-to-end offline: build one cited report under the local profile
make run-api       # FastAPI on 127.0.0.1:8103 (local profile binds loopback by default)
```

The agent card is served at `GET /.well-known/agent-card.json` and the health probe at
`GET /healthz` (reports the active profile, market and vertical).

## 2. Deploy (managed stack)

```bash
# 1. Provision infra (review the plan; the WORM bucket lock is irreversible when
#    locked = true, the default).
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars   # set project_id, org_id, access_policy_id
terraform init -input=false && terraform plan
terraform apply

# 2. Export the outputs the app reads.
export GOOGLE_CLOUD_PROJECT="$(terraform output -raw project_id)"
export MKT_PERF_REGION="$(terraform output -raw region)"
export MKT_PERF_KMS_KEY="$(terraform output -raw kms_key)"
export MKT_PERF_BQ_DATASET="$(terraform output -raw bigquery_dataset)"
export MKT_PERF_LOG_BUCKET="$(terraform output -raw log_bucket)"

# 3. Install the managed stack and run the API.
pip install -e ".[gcp,dev]"
export GOOGLE_CLOUD_PROJECT=your-sg-project MKT_PERF_PROFILE=gcp
gcloud auth application-default login
make run-api PROFILE=gcp          # FastAPI on :8103 (front with the platform ingress)
```

For a quick project-scoped evaluation WITHOUT org-level prerequisites, set `enable_vpc_sc =
false` and the audit bucket `locked = false` so everything stays deletable (not compliant for
production). See `infra/terraform/terraform.tfvars.example` and `infra/terraform/README.md`.

The ADK agent is deployed to Agent Runtime separately via the Agent Platform SDK; see the
docstring in `src/performance_marketing/agent/root_agent.py`. Record the resulting
`reasoningEngine` resource name in `settings.agent_engine.resource_name` (or `MKT_AGENT_ENGINE`).
To attach an out-of-process governed MCP tool server, set `MKT_PERF_MCP_SERVER_URL`; unset, the
agent uses its in-process FunctionTools.

## 3. Region selection and fail-fast

The Terraform `region` is validated against the residency allowlist; an apply against a region
outside it fails at `terraform plan`, before anything is created. BigQuery, Vertex, Cloud
Logging and the WORM bucket are all created in the selected region, and a `gcp.resourceLocations`
Org Policy hard-restricts resource creation to it. The app also validates the active market's
region at load, so a mismatched deploy fails fast on both sides.

## 4. Key rotation, retention and the WORM lock

The CMEK crypto key (`kms.tf`) rotates on schedule; rotation is transparent to the app. The
audit bucket retention is `retention_days` (default 2557, ~7 years) and the bucket is
`locked = true` by default, which is **irreversible**. To trial without locking, set
`locked = false` (not compliant for production). Only screened prompts and responses are ever
written to the audit log.

## 5. Kill switch

To stop serving without tearing down state: scale the Cloud Run / Agent Runtime deployment to
zero, or remove the app service account's `roles/aiplatform.user` binding. The audit trail
remains intact.

## 6. Common failures

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `NotImplementedError` from a CLI command (exit 2) | `MKT_PERF_PROFILE=onprem` with placeholder adapters | Set `MKT_PERF_PROFILE=gcp` (or implement the on-prem adapter) |
| `UnknownAccountError` on a report (HTTP 404) | No such account in the ad-platform source | Confirm the `account_id` and its market / vertical |
| `MetricsEmptyError` on a report (HTTP 404) | No metrics in the lookback window | Widen `lookback_days` or confirm the metrics source is populated |
| Guardrail block on a benign request (HTTP 400) | Model Armor template too strict | Tune the `model_armor` template filter confidence levels |
| VPC-SC denies the apply | Runner identity outside the perimeter | Apply with `vpc_sc_enforce = false`, add the identity to `operator_members`, re-apply true |
