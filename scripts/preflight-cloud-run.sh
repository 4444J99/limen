#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:-${GOOGLE_CLOUD_PROJECT:-device-streaming-067d747a}}"
REGION="${GCP_REGION:-us-central1}"
SERVICE_NAME="${LIMEN_CLOUD_RUN_SERVICE:-limen-api}"

REQUIRED_SERVICES=(
  "run.googleapis.com"
  "secretmanager.googleapis.com"
  "cloudbuild.googleapis.com"
  "artifactregistry.googleapis.com"
)

REQUIRED_SECRETS=(
  "limen-github-token"
  "limen-api-token"
  "limen-client-token"
)

failures=0

note() {
  printf '%s\n' "$*"
}

fail() {
  failures=$((failures + 1))
  printf 'FAIL: %s\n' "$*" >&2
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    fail "missing command: $1"
    return 1
  fi
}

gcloud_quiet() {
  gcloud "$@" --quiet 2>/dev/null
}

billing_enabled() {
  local value=""
  if value="$(gcloud_quiet billing projects describe "$PROJECT_ID" --format='value(billingEnabled)')"; then
    [[ "$value" == "True" || "$value" == "true" ]]
    return
  fi
  if value="$(gcloud_quiet beta billing projects describe "$PROJECT_ID" --format='value(billingEnabled)')"; then
    [[ "$value" == "True" || "$value" == "true" ]]
    return
  fi
  return 1
}

note "Cloud Run preflight"
note "project: ${PROJECT_ID}"
note "region: ${REGION}"
note "service: ${SERVICE_NAME}"

require_command gcloud || exit 1

if ! gcloud_quiet projects describe "$PROJECT_ID" --format='value(projectId)' >/dev/null; then
  fail "cannot read GCP project ${PROJECT_ID}; check auth and project access"
fi

if billing_enabled; then
  note "billing: enabled"
else
  fail "billing is not enabled or cannot be verified for ${PROJECT_ID}; Cloud Run/source deploy and required APIs will not work"
fi

enabled_services="$(gcloud_quiet services list --enabled --project "$PROJECT_ID" --format='value(config.name)' || true)"
for service in "${REQUIRED_SERVICES[@]}"; do
  if printf '%s\n' "$enabled_services" | grep -Fxq "$service"; then
    note "service enabled: ${service}"
  else
    fail "required API is not enabled: ${service}"
  fi
done

for secret in "${REQUIRED_SECRETS[@]}"; do
  if gcloud_quiet secrets describe "$secret" --project "$PROJECT_ID" --format='value(name)' >/dev/null; then
    note "secret present: ${secret}"
  else
    fail "required Secret Manager secret is missing: ${secret}"
  fi
done

if gcloud_quiet run services describe "$SERVICE_NAME" --project "$PROJECT_ID" --region "$REGION" --format='value(status.url)' >/dev/null; then
  note "existing service: ${SERVICE_NAME}"
else
  note "existing service: ${SERVICE_NAME} not found; first deploy can create it after preflight passes"
fi

if [[ "$failures" -gt 0 ]]; then
  printf '\nPreflight failed with %s issue(s). Fix GCP billing, required APIs, and secrets before deploying the hosted API.\n' "$failures" >&2
  exit 1
fi

note "preflight: ok"
