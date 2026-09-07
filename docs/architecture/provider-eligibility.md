# Provider eligibility admission

Status: bounded implementation, not production policy activation.

`provider_eligibility` is an optional, strict, versioned execution input. It binds
data classification, maximum retention, exact tool names and HTTPS destination
origins to one repository and immutable source revision. A policy-bearing execution uses
`limen-execution-contract.v5`; missing/null policies preserve the historical v4
fingerprint. Legacy compatibility is **not** a claim that retention or data
eligibility has been verified for those tasks.

`limen.provider_eligibility` validates the request and evaluates an independently
authenticated evidence statement bound to provider, actual observed model ID,
policy digest, source revision, permitted scope, issue time and expiration.
Type-valid JSON, a digest, an authority-reference string, or `verified: true`
does not authenticate a statement. The verifier is supplied by a trusted adapter,
never deserialized from an agent task. Synthetic test verifiers prove only the
deterministic admission seam.

The existing provider selector can filter candidates through this predicate
before capability/health/cost ranking. A denied model cannot win by being more
capable, cheaper, or named in an override. No model constants, provider resource
registry, or second scheduler are introduced.

There is currently **no installed production attestation adapter**. Accordingly,
policy-bearing tasks fail closed before reservation or launch with
`provider_eligibility_adapter_unavailable`; malformed policies return
`provider_eligibility_invalid`. A caller cannot activate this path by putting a
synthetic attestation or verifier flag in its task. The existing canonical
reservation and budget machinery remains authoritative.

Activation requires an approved adapter that independently authenticates current
account/provider policy, source authorization, effective tool/destination limits
and retention eligibility. Its actual provider invocation must revalidate the
exact contract and selected model after acknowledged reservation. Until those
adapter and hosted canaries exist, C2 is partial and provider deployment remains
unavailable for policy-bearing tasks.

Focused seam diagnostics: `pytest cli/tests/test_provider_eligibility.py`.
These tests are synthetic and do not establish entitlement, platform settings,
data-retention behavior, hosted execution or publication authority.
