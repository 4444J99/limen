# Execution policy binding storage

Owner: [#3022](https://github.com/4444J99/limen/pull/3022).
Code: `web/worker/src/conduct/execution-policy-storage.js` and
`cli/src/limen/execution_policy.py`.

`LIMEN_EXECUTION_POLICY` accepts legacy object JSON, or a versioned transport envelope:

```json
{
  "schema_version": "limen.execution_policy_storage.v1",
  "encoding": "gzip+base64",
  "sha256": "<SHA-256 of decoded UTF-8 JSON bytes>",
  "uncompressed_bytes": 5348,
  "data": "<canonical base64 of gzip bytes>"
}
```

The envelope is transport, never admission policy. The encoder emits at most 5,000
UTF-8 bytes, conservatively below the provider's
[5 KB variable limit](https://developers.cloudflare.com/workers/platform/limits/#environment-variables).
It keeps smaller policies as plain JSON and rejects incompressible policies that
still exceed that limit. The reader accepts envelopes up to 5,120 bytes and
decoded policies up to 65,536 bytes. Legacy object JSON remains supported within
the decoded cap, including whitespace already present in an installed binding.

Decoding validates exact envelope fields, supported schema and encoding, canonical
base64, gzip integrity, declared and maximum decoded length, SHA-256, strict UTF-8,
and an object JSON result. Nested transport envelopes are rejected. Stream reading
stops and cancels at the declared length bound; an invalid payload never becomes
the admission policy. All decoder errors use a fixed redacted classification.
The implementation uses the Worker's native
[compression streams](https://developers.cloudflare.com/workers/runtime-apis/web-standards/#compression-streams)
and Web Crypto, with no new runtime dependency or compatibility flag.

Each keeper instance resolves one decoded policy snapshot before handling service
requests or alarms. Admission receives that snapshot. Authenticated policy readback
computes the existing canonical semantic fingerprint of the same object, independent
of storage representation. Private policy recovery still requires the existing
conductor role and explicit custody header. Ordinary readback reveals no policy
body and includes `supported_storage_encodings: ["json", "gzip+base64"]`.
Invalid storage leaves admission fail closed and returns `execution_policy_invalid`
with HTTP 409 from readback.

## Installation and rollback

The reconciliation command's default remains read-only. It computes transport size
before invoking Wrangler, preserves exact source/live fingerprint comparison, and
refuses a compressed installation unless authenticated live readback advertises the
decoder. It rechecks the full live generation immediately before its write and
verifies the canonical candidate fingerprint afterward. The provider has no CAS
for this secret, so exclusive policy ownership remains required.

Deployment is a separate operator gate:

1. Review and approve the exact compatible reader code deployment.
2. Deploy that reader while retaining the existing legacy policy. Verify runtime
   identity, legacy policy fingerprint and advertised encoding support.
3. Prepare the approved candidate through the new encoder under its existing
   source/candidate fingerprints. Approval does not remove live generation fencing.
4. Install only within the approved policy scope; verify the exact semantic
   candidate fingerprint and preserved priorities through private readback.

Before activation of compressed storage, a code rollback can retain legacy policy.
After activation, restore the verified prior legacy policy before rolling back to
code without the decoder. Do not roll old code back with compressed storage active.
No worker deployment, policy update or custody action is performed by tests.

## Verification

`npm run check` in `web/worker` covers full Worker behavior plus the new policy
roundtrip and negative cases. `cli/tests/test_execution_policy.py` covers deterministic
bounded encoding, unchanged decoded values, incompressible/oversize failures and
reader capability fencing. The owning scoped resolver also selects Python lint,
format, syntax and applicable governance predicates.
