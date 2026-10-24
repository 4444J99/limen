# Native prefix lineage check

Owner: [#3056](https://github.com/4444J99/limen/issues/3056); publication: [draft #3087](https://github.com/4444J99/limen/pull/3087).

The visible openers of L08 and L22 now match the first retained candidate user prompts in
their existing compressed native files. This is a narrower positive result than full lineage
or original pre-retention completeness.

| Source | First candidate source line | Text characters | Full body matches native reader | Native turn matches |
|---|---:|---:|---|---|
| L08 | 9 | 6,992 | Yes | Yes |
| L22 | 9 | 11,036 | Yes | Yes |

The first metadata record also matches the fingerprint retained in the existing header index
for each source. Both records identify CLI sources with paginated history. Neither metadata
record carries an explicit fork/parent field, but its absence does not prove that no such
relationship exists. No per-item human authorship is inferred from a user role.

The files were read in place. Each source's inode, size and modification time stayed unchanged
during the reads. Metadata decoding was capped at 256 KiB compressed input and 4 MiB decoded
record size. The separate prompt-prefix read was capped at 1 MiB compressed input, 2 MiB
decompressed output, 256 records and five seconds. Existing derived-frame prefix rules were
applied before selecting the first candidate user prompt. Actual prompt-prefix reads consumed
80 KiB and 96 KiB of compressed input. No original bulk-capture bound was raised.

The [machine-readable receipt](native-prefix-lineage-v1.json) contains source aliases and scoped
results. Private native paths, turn/item identifiers and source-stat evidence remain in the
private binding index. No prompt body, instruction body, archive, or new transcript copy was
written.

This proves the visible opener's exact retained-file binding. It does not prove source EOF,
the original pre-retention opener, complete side histories, full reply retention, or whole-file
byte custody. The earlier source-limit dispositions remain intact: a readable bounded prefix
does not repair an oversized later record.
