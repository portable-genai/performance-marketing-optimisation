# infra/terraform - Mkt4 Performance Marketing deploy and residency hardening

This Terraform stack makes the deployed posture of Mkt4 enforceable at `terraform plan` time,
not merely documented. It deploys the FastAPI service (container port 8103) to Cloud Run in an
in-country APAC region, with residency pinned, CMEK bound end to end, a dry-run-first VPC-SC
perimeter, WORM audit logging and posture alerts.

A control that lives only in a document is not a control: each resource carries a comment
mapping it to the relevant guarantee in `SPEC.md` ("Guarantees": provenance, maker-checker,
WORM audit, region validation against the per-market allow-list).

## What gets created

| File | Purpose |
| --- | --- |
| `providers.tf` | Google / google-beta providers, pinned to `var.region` (never global). |
| `variables.tf` | The only knobs. `region` is allow-list validated to fail fast. |
| `terraform.tfvars.example` | Fictional in-country defaults; copy to `terraform.tfvars`. |
| `apis.tf` | Enables ONLY the managed services the gcp profile binds (see below). |
| `org_policy.tf` | `gcp.resourceLocations` allow-list + disable SA-key creation + uniform bucket access. |
| `kms.tf` | One regional CMEK key + a per-service IAM binding (no project-wide grant). |
| `bigquery.tf` | The metrics warehouse (MetricsPort), in-region, CMEK-encrypted. |
| `vpc_sc.tf` | Service perimeter, dry-run first (`vpc_sc_dry_run = true`). |
| `logging_worm.tf` | Locked (WORM) Cloud Logging bucket + sink + data-access audit config. |
| `monitoring.tf` | Log-based alerts: guardrail blocks, SA-key creation, VPC-SC denials, CMEK changes. |
| `iam.tf` | Least-privilege Cloud Run runtime service account. |
| `cloud_run.tf` | The FastAPI service: runtime SA, `MKT_PERF_PROFILE=gcp`, CMEK, internal ingress, port 8103, `/healthz` probes. |
| `outputs.tf` | Values to wire into the runtime environment after apply. |

There is no `agent_runtime.tf`: `src/performance_marketing/agent/` contains no reasoning-engine
runtime to deploy (the A2A / MCP governance ports are served by the same Cloud Run process).

## APIs enabled and why (tied to the gcp adapters)

`apis.tf` enables only the services bound under `config/settings.yaml` `adapters: ... gcp:`:

| Service | Adapter / port it serves |
| --- | --- |
| `bigquery.googleapis.com` | `metrics` (BigQueryMetricsAdapter): the metrics warehouse. |
| `aiplatform.googleapis.com` | `ad_platform` (Vertex AI forecasting), `llm` (Gemini), `evaluation` (Gen AI eval), `agent_registry` (A2A). |
| `modelarmor.googleapis.com` | `guardrail` (Model Armor). |
| `logging.googleapis.com` | `audit` (Cloud Logging WORM). |
| `cloudtrace.googleapis.com` | `tracer` (Cloud Trace). |
| `run.googleapis.com` | serves the FastAPI app. |
| `cloudkms`, `orgpolicy`, `accesscontextmanager`, `artifactregistry`, `compute`, `iam`, `monitoring` | core residency / CMEK / perimeter / image / alerting plumbing. |

### A note on the ad platform and egress

In the gcp profile the `AdPlatformPort` is backed by Vertex AI forecasting, a GCP API
(`aiplatform`), so it needs no public egress and sits inside the perimeter. If a deployment
instead points the `AdPlatformPort` at an EXTERNAL ad-network SaaS (Google Ads, Meta, etc.),
that call leaves the perimeter over the internet and must be allowed as controlled egress (a
VPC-SC egress rule or Private Service Connect), NOT by enabling another GCP API here.

## Residency

`var.region` is validated against the per-market APAC allow-list, identical to
`config/settings.yaml` `markets.*.region` and `config.market_profile()`:

- SG -> `asia-southeast1` (default)
- JP -> `asia-northeast1`
- AU -> `australia-southeast1`

The same allow-list is enforced in the app at settings load, so an off-region value fails fast
in both code and infra. One project deploys one market.

## Usage

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars   # then edit project_id etc.

terraform init
terraform plan                                  # or: make tf-plan  (from repo root)
terraform apply
```

`make tf-plan` (repo root) runs `terraform plan` for the pinned region so the posture is
checked the same way locally and in CI.

## VPC-SC rollout (dry-run first)

1. Apply with `enable_vpc_sc = false` (default) to build everything.
2. Set `enable_vpc_sc = true` with `vpc_sc_dry_run = true` (default): the perimeter is created
   in audit-only mode. Watch the audit logs for would-be denials.
3. Add your Terraform runner / CI identity to an access level.
4. Once the dry-run window is clean, set `vpc_sc_dry_run = false` to enforce.

Never enforce blind on a path you have not first watched in dry-run.

## Irreversible actions

- `logging_worm.tf` sets `locked = true` on the audit bucket: retention cannot be reduced and
  the bucket cannot be deleted for the full window. Confirm `retention_days` before apply.
- `kms.tf` sets `prevent_destroy = true` on the CMEK key: a destroyed key strands all
  CMEK-encrypted data.

## Image

The Cloud Run service runs the image built by the repo `Dockerfile` (port 8103,
`MKT_PERF_PROFILE=gcp`). Build and push to the in-region Artifact Registry, then set
`container_image` to the fully-qualified tag.
