# AI Chat Exporter — Public Evidence Packet

## Bounded claim

AI Chat Exporter is a privacy-first, client-side conversation export tool. The public product
surface presents five export formats: Markdown, HTML, JSON, PNG, and text. This claim does not imply
installations, daily users, revenue, retention, or cloud-free behavior beyond the documented
client-side export path.

## Inspectable evidence

- Architecture and implementation: [public source](https://github.com/organvm-iii-ergon/a-i-chat--exporter).
- Exact-head verification: [successful workflow run](https://github.com/organvm-iii-ergon/a-i-chat--exporter/actions/runs/29999319405)
  at `e3a0b8d9a47183163cd92d18f479fc580eaf314d`.
- Public installation surface: [live product page](https://organvm-iii-ergon.github.io/a-i-chat--exporter/).

## Metric treatment

The five-format count is verified against the public product surface. The verifier checks every
format name rather than treating a landing-page HTTP response as enough evidence. Reproduce it
with `python3 scripts/flagship-evidence.py --verify-live --json`.

## Authorship and limitations

The public packet confines the claim to inspectable client-side behavior and avoids any user-volume
inference.

- Five formats do not prove daily use, installations, revenue, or user retention.
- The packet makes no claim about the commercial availability or uptake of optional workflows.

## Withdrawal route

If any required format term disappears from the public surface or the workflow/endpoint fails,
withdraw the metric statement until a freshly reviewed packet restores a reproducible source.
