# Scheduled process census under host pressure

The accepted #2852 activation reached the corrected observer but its supervisor
failed closed after 611ms with an unavailable boundary. This is consistent with the
old 0.5-second process-census deadline; that receipt does not retain the causal stage.
Preserve the failed receipt and add sanitized census stages to future failure reasons.

Give mandatory RSS and descendant censuses up to three seconds, capped by the
remaining original wall budget. Do not raise wall, CPU, memory or output limits; do
not skip census or allow unknown descendants. Add regressions for a valid slow census
and unavailable census still terminating and reaping its owned child. Retain the
existing resource, CPU, output, timeout and descendant-cleanup regressions.

Merge the exact tested head, install the accepted immutable runtime, use the normal
reviewed activation lifecycle, retain its controlled smoke receipt, then witness the
first naturally due 900-second maintenance observation. Domus #423 supplies the
separately tested five-second capability startup bound. Existing human sessions remain
protected, and the sole 24-hour read-only app watch remains owned by the recovery chat.

Validation: initial six focused shards passed 70 tests. The stage-only followup passed
34 of 37 tests twice; three unchanged CPU/descendant timing fixtures could not finish
on the protected host (load209, swap14.4GiB). Eleven implicated cheap gates pass;
check-effectors exhausted its finite180s deadline. Broad heavy shards were not
reached/admitted. These resource-limited outcomes remain visible, not passing claims.
