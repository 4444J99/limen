# Closeout source denominator

Owner: L-CLOSEOUT-OBSERVE-ARM / this PR. Preserve done claims without PR references so the existing UNRECEIPTED classifier sees them. Session source selection now applies latest-record identity before closure filtering, preventing reopened sessions from remaining false done claims. No broker task transition or external write is added. Malformed/missing source coverage and authoritative acceptance receipt ingestion remain separate incomplete requirements; these changes do not establish full closeout acceptance.
