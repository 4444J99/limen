# Downs Style Studio

A private, shareable editorial studio for Charles Downs. It brings the complete
public Downs Style history, an evidence-backed voice system, and the current
rosewater article into one coherent review surface.

## Pages

- `/` — the six-product rosewater article, including Fresh and its affiliate disclosure
- `/archive` — all 258 public posts, searchable and filterable by category and year
- `/voice` — the corpus → Natural Center → channel-profile voice architecture
- `/compare` — the preserved three-panel rosewater draft comparison
- `/cotton` — the cotton-only article, recreation shot list, SEO package, and current social launch language

The archive stores public metadata only: publication date, year, category,
title, canonical Downs Style URL, author, and word count. Article bodies and raw
tags are deliberately excluded.

## Prerequisites

- Node.js `>=22.13.0`

## Quick Start

```bash
npm install
npm run dev
npm run build
```

This starter does not use `wrangler.jsonc`.

## Project shape

- `app/` contains the rose article, cotton article, archive, voice, comparison, and shared navigation
- `data/posts.json` is the bounded 258-record public ledger
- `tests/rendered-html.test.mjs` verifies complete server-rendered routes and data integrity
- `.openai/hosting.json` preserves the existing Sites project identity

## Useful Commands

- `npm run dev`: start local development
- `npm run build`: verify the vinext build output
- `npm test`: build and verify all rendered routes plus archive integrity

The studio is a review artifact. It does not modify or publish the live
Squarespace site. The cotton route is explicitly `noindex`; its Pexels images
are composition references for Charles to recreate, not final publication art.
