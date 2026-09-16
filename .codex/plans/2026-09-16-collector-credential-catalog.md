# Collector credential catalog

The production collector consumes LIMEN_INVENTORY_COLLECTOR_TOKEN, but the credential Wall catalog omitted it. Add an explicit entry with collector-only role, owning issues, and unverified custody/installation. Do not invent a 1Password item path, reuse an ordinary principal, mint a token, or activate ingestion. The 250-item ceiling and 900-second freshness remain unchanged. This is discoverability and ownership, not collector provisioning or acceptance.

Owner: this PR and credential Wall #320; production acceptance remains #269/#1995. Validate through the scoped gate batch before landing.
