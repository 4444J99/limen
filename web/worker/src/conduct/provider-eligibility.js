// Canonical intake validation, not provider attestation or launch authority.
// Keep the policy normalization contract aligned with limen.provider_eligibility.
const POLICY_VERSION = "limen.provider_eligibility.v1";
const POLICY_KEYS = [
  "schema_version", "repository", "source_revision", "data_classification",
  "max_retention_days", "tools", "destinations",
].sort();
const CLASSES = new Set(["synthetic", "public", "internal", "confidential", "restricted"]);
const IDENTIFIER = /^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$/;
const REPOSITORY = /^[A-Za-z0-9][A-Za-z0-9_.-]*\/[A-Za-z0-9][A-Za-z0-9_.-]*$/;

export class ProviderEligibilityError extends Error {}

function reject() {
  throw new ProviderEligibilityError("provider_eligibility_invalid");
}

function fullmatch(pattern, value) {
  // JS `$` also matches before a terminal newline; Python fullmatch does not.
  return typeof value === "string" && value.match(pattern)?.[0] === value;
}

function exactOrigin(value) {
  if (!value.startsWith("https://") || /[\s*\\\u0000-\u001f\u007f]/u.test(value)) reject();
  const authority = value.slice(8);
  const match = authority.match(/^(\[[0-9A-Fa-f:.]+\]|[^:/@?#\[\]]+)(?::([0-9]+))?$/u);
  if (!match || match[0] !== authority) reject();
  const [, host, port] = match;
  if (port !== undefined && Number(port) > 65535) reject();
  if (host.startsWith("[")) {
    try {
      // WHATWG and urlsplit agree on bracketed IPv6; neither reinterprets a
      // DNS spelling or strips an explicit default port from retained scope.
      new URL(value);
    } catch {
      reject();
    }
  } else if (/[:/@?#]/u.test(host.normalize("NFKC"))) {
    reject();
  }
}

function scope(value, origins = false) {
  if (!Array.isArray(value) || value.some((item) => typeof item !== "string")
      || new Set(value).size !== value.length) reject();
  for (const item of value) {
    if (origins) exactOrigin(item);
    else if (!fullmatch(IDENTIFIER, item)) reject();
  }
  return [...value].sort();
}

export function validateProviderEligibility(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)
      || JSON.stringify(Object.keys(value).sort()) !== JSON.stringify(POLICY_KEYS)
      || value.schema_version !== POLICY_VERSION
      || !fullmatch(REPOSITORY, value.repository)
      || !fullmatch(/^[0-9a-f]{40}$/, value.source_revision)
      || !CLASSES.has(value.data_classification)
      || !Number.isInteger(value.max_retention_days)
      || value.max_retention_days < 0 || value.max_retention_days > 36500) reject();
  return {
    schema_version: POLICY_VERSION,
    repository: value.repository.toLowerCase(),
    source_revision: value.source_revision,
    data_classification: value.data_classification,
    max_retention_days: value.max_retention_days,
    tools: scope(value.tools),
    destinations: scope(value.destinations, true),
  };
}

export function validateProviderEligibilityUpdate(existing, candidate) {
  const next = candidate.provider_eligibility == null
    ? null : validateProviderEligibility(candidate.provider_eligibility);
  if (existing?.provider_eligibility != null) {
    const prior = validateProviderEligibility(existing.provider_eligibility);
    if (JSON.stringify(next) !== JSON.stringify(prior)) {
      throw new ProviderEligibilityError("provider_eligibility_change_unauthorized");
    }
  }
  if (next !== null && (typeof candidate.repo !== "string" || candidate.repo.toLowerCase() !== next.repository)) {
    throw new ProviderEligibilityError("provider_eligibility_repository_mismatch");
  }
  return next;
}
