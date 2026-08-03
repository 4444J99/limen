# Downs Style public-post archive audit

**Verified:** August 2, 2026

**Result:** 258 public dated posts, spanning December 4, 2017 through August 2, 2026

This is the complete public archive visible through Downs Style's live dated-post surfaces at the time of the audit. It is an evidence set for Charles's writing system—not a claim about private drafts, deleted pages, or sole authorship.

## Completeness result

- 258 unique canonical post URLs were independently enumerated across the [XML sitemap](https://www.downsstyle.com/sitemap.xml), the homepage, and all nine paginated Squarespace collection feeds.
- The sitemap exposed 257 posts. The collection feeds exposed all 258.
- The one post missing from the sitemap was the August 2, 2026 rose-water post; both its collection feed and the homepage exposed it.
- Every URL returned HTTP 200. There were no fetch or parse failures, no redirects, no empty extracted bodies, and no duplicate nonempty extracted-body SHA-256 fingerprints.
- All 258 live pages carried the author metadata `Chas Downs`.
- The smallest extracted post was 50 words; the largest was 1,195. The median across all public posts was 265 words.

The completeness claim is deliberately bounded: it covers public dated-post pages reachable through the site's live collection architecture on the verification date. A private, draft, deleted, or completely unlinked page cannot be proven absent from public-facing evidence alone.

## Archive by category

| Category | Posts | Share |
| --- | ---: | ---: |
| Skincare | 112 | 43.4% |
| Masks | 51 | 19.8% |
| Look Book | 36 | 14.0% |
| Candles | 18 | 7.0% |
| Eat | 12 | 4.7% |
| Interior Design | 8 | 3.1% |
| Gift Inspo | 7 | 2.7% |
| Travel | 7 | 2.7% |
| Workouts/Diet | 7 | 2.7% |
| **Total** | **258** | **100.0%** |

Skincare and masks together account for 163 posts, or 63.2% of the archive. Clothing is still a meaningful established lane through the 36-post Look Book collection, while the 18 candle posts give the proposed candle-care article a real historical home.

## Archive by year

| Year | Posts |
| --- | ---: |
| 2017 | 16 |
| 2018 | 78 |
| 2019 | 22 |
| 2020 | 54 |
| 2021 | 22 |
| 2022 | 5 |
| 2023 | 36 |
| 2024 | 24 |
| 2025 | 0 |
| 2026 | 1 |
| **Total** | **258** |

## Evidence architecture

The archive now feeds a three-stage system:

1. **Corpus and provenance:** [downs-style-post-ledger.csv](downs-style-post-ledger.csv) records public metadata, discovery rails, status, word counts, and content fingerprints.
2. **Voice assembly:** [downs-style-voice-metrics.json](downs-style-voice-metrics.json) contains aggregate, non-verbatim measurements; [downs-style-natural-center.yaml](downs-style-natural-center.yaml) turns those measurements into a computable identity.
3. **Channel style sheet:** [downs-style-channel-profile.yaml](downs-style-channel-profile.yaml) translates the Natural Center into website and myth-callout rules. [downs-style-voice-evidence.md](downs-style-voice-evidence.md) keeps every major editorial decision traceable to evidence.

The raw article-body corpus was created only as a transient local analysis input and is not tracked. No article body appears in these deliverables. Historic tags remain in the provenance ledger, but they were excluded from voice derivation because the site's tag field is noisy and often mechanically expanded.

## Causal baseline

The voice baseline includes 257 posts published through December 31, 2024. It intentionally excludes the August 2, 2026 rose-water post because that article was produced before this audit; including it would let newer assisted copy teach the system what it was supposed to discover from Charles's earlier history.

The baseline contains 76,597 alphabetic tokens. Sentence and paragraph boundaries are heuristic because older pages mix prose, lists, and shopping modules. Phrase counts are literal and case-insensitive. These measurements describe the published corpus; they do not establish that every claim in it was true or that every word had one author.

## Reproduction

```sh
python3 scripts/audit-downs-style-archive.py \
  --output docs/continuations/charles/downs-style-post-ledger.csv \
  --corpus-json /tmp/downs-style-corpus.json

python3 scripts/analyze-downs-style-voice.py \
  --corpus-json /tmp/downs-style-corpus.json \
  --output docs/continuations/charles/downs-style-voice-metrics.json \
  --baseline-cutoff 2024-12-31
```

Current artifact fingerprints:

- Ledger SHA-256: `00568b0f472b0e6cf7792064c40a1f8c32dde764195109e27d507684bd88dcad`
- Metrics SHA-256: `65e090919ea2eb44e3f565f09a51f1f145bc6cac99a81cd598a662c4e9bbd98e`
