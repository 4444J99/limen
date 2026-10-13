# Restore exact private witness source checkout

The #2853 witness-contract job failed at checkout, before executing tests. Live API
metadata confirms organvm/ops-witness redirects to private4444J99/ops-witness; the
pinned75af87fe7e47d76d005f985c19d5c20be09e6266 exists. Use canonicalidentity and
the alreadyregistered OPS_SOURCE_GITHUB_TOKEN only for this immutablecheckout,
with persist-credentialsfalse. Keep providercredentials confined to their existing
accepted-default-branch observer. Tighten the workflow guard to permit this one
sourcecheckoutcredential and reject other secret uses. No credentialminting,
providerwrites, permissionexpansion, skippedcapability or runtime restart.

Validate the credentialconfinement and scopedworkflow predicates; merge the exact
head on the existing Limenfastlane. Runtime482e97 remains unchanged during its
natural maintenance witness; CI-onlysource delivery does not reset its cadence.
